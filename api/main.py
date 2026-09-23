"""FastAPI backend for the Money Graph analyst interface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import assistant
from .cards import build_card
from .graph_store import GraphStore, StoreUnavailable


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
WEB = ROOT / "web"

app = FastAPI(title="Money Graph API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/web", StaticFiles(directory=WEB), name="web")

store = GraphStore(OUT)

# Compatibility aliases for direct-call tests; assistant.py moves to GraphStore in Block D.
graph_data: dict[str, Any]
nodes_by_id: dict[str, dict[str, Any]]
clusters_data: list[dict[str, Any]]
top_data: list[dict[str, Any]]
summary_data: dict[str, Any]
resilience_data: dict[str, Any]
graph: Any


def _sync_aliases() -> None:
    global graph_data, nodes_by_id, clusters_data, top_data, summary_data, resilience_data, graph
    graph_data = store.graph_data
    nodes_by_id = store.nodes_by_id
    clusters_data = store.clusters
    top_data = store.top
    summary_data = store.summary
    resilience_data = store.resilience
    graph = store.graph


_sync_aliases()


class CommonRequest(BaseModel):
    gids: list[str] = Field(min_length=1, max_length=20)


class AssistantRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)


def _service_call(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return function(*args, **kwargs)
    except StoreUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _node_call(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return _service_call(function, *args, **kwargs)
    except KeyError as error:
        gid = str(error.args[0])
        raise HTTPException(status_code=404, detail=f"gid {gid} не найден") from error


def reload_data() -> None:
    store.reload()
    _sync_aliases()


def llm_status() -> tuple[bool, str | None]:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY")), provider
    if provider == "nvidia":
        return bool(os.getenv("NVIDIA_API_KEY")), provider
    available = bool(os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY"))
    return available, None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    available, provider = llm_status()
    return {"status": "ok", "out_loaded": store.loaded, "llm_available": available, "provider": provider}


@app.get("/api/summary")
def get_summary() -> dict[str, Any]:
    return _service_call(lambda: (store.require_loaded(), store.summary)[1])


@app.get("/api/graph")
def get_graph(min_kzt: Annotated[float, Query(ge=0)] = 0) -> dict[str, Any]:
    return _service_call(store.graph_payload, float(min_kzt))


@app.get("/api/search")
def search(q: Annotated[str, Query(max_length=80)] = "") -> list[dict[str, Any]]:
    return _service_call(store.search, q)


@app.get("/api/node/{gid}")
def get_node(gid: str) -> dict[str, Any]:
    return _node_call(store.node, str(gid))


@app.get("/api/top")
def get_top(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    role: str | None = None,
    cluster: int | None = None,
    exclude_seed: bool = False,
) -> list[dict[str, Any]]:
    return _service_call(store.top_nodes, limit, role, cluster, exclude_seed)


@app.get("/api/clusters")
def get_clusters() -> list[dict[str, Any]]:
    return _service_call(lambda: (store.require_loaded(), store.clusters)[1])


@app.get("/api/cluster/{cluster_id}")
def get_cluster(cluster_id: int) -> dict[str, Any]:
    try:
        return _service_call(store.cluster, cluster_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"cluster {cluster_id} не найден") from error


@app.get("/api/resilience")
def get_resilience() -> dict[str, Any]:
    return _service_call(store.resilience_payload)


@app.get("/api/cycles")
def get_cycles(gid: str | None = None) -> list[list[str]]:
    return _service_call(store.cycles_for, str(gid) if gid is not None else None)


@app.post("/api/reload")
def reload_endpoint() -> dict[str, Any]:
    reload_data()
    if not store.loaded:
        raise HTTPException(status_code=503, detail=store.error)
    return {"ok": True, "nodes": len(store.nodes_by_id), "edges": store.graph.number_of_edges()}


@app.post("/api/pipeline/run")
def run_pipeline() -> dict[str, Any]:
    started = time.perf_counter()
    command = [sys.executable, "-m", "pipeline", "--data", str(ROOT / "data"), "--out", str(OUT)]
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as error:
        raise HTTPException(status_code=500, detail="Pipeline exceeded the 300 second timeout") from error
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr[-2000:] or "Pipeline failed")
    reload_data()
    if not store.loaded:
        raise HTTPException(status_code=500, detail=store.error)
    roles = store.summary.get("role_counts", store.summary.get("roles", {}))
    return {"ok": True, "elapsed_sec": round(time.perf_counter() - started, 3), "roles": roles}


@app.get("/api/node/{gid}/card")
def get_node_card(gid: str) -> dict[str, Any]:
    node = get_node(gid)
    return build_card(str(gid), node, node["incoming"], node["outgoing"], store.nodes_by_id)


@app.get("/api/node/{gid}/ego")
def get_ego(
    gid: str,
    k: Annotated[int, Query(ge=1, le=3)] = 1,
    direction: str = "both",
    max_nodes: Annotated[int, Query(ge=1, le=300)] = 300,
) -> dict[str, Any]:
    if direction not in {"up", "down", "both"}:
        raise HTTPException(status_code=400, detail="direction must be up, down, or both")
    return _node_call(store.ego, str(gid), k, direction, max_nodes)


@app.get("/api/path")
def get_path(src: str, dst: str) -> dict[str, Any]:
    try:
        return _node_call(store.shortest_path, str(src), str(dst))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/common")
def get_common(request: CommonRequest) -> dict[str, Any]:
    # Block B expands this response to two hops with amount summaries.
    gids = [str(gid) for gid in request.gids]
    for gid in gids:
        get_node(gid)
    receivers = [{str(item) for item in store.graph.successors(gid)} for gid in gids]
    senders = [{str(item) for item in store.graph.predecessors(gid)} for gid in gids]
    return {
        "gids": gids,
        "common_receivers": sorted(set.intersection(*receivers)) if receivers else [],
        "common_senders": sorted(set.intersection(*senders)) if senders else [],
    }


@app.post("/api/assistant")
def ask_assistant(request: AssistantRequest) -> dict[str, Any]:
    try:
        return assistant.answer(request.question, request.history)
    except assistant.llm.LLMUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/node/{gid}/card/llm")
def explain_card(gid: str) -> dict[str, Any]:
    card = get_node_card(gid)
    try:
        result = assistant.answer(
            "Составь краткую справку только по фактам этой карточки: " + json.dumps(card, ensure_ascii=False), []
        )
    except assistant.llm.LLMUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    result["evidence"] = card.get("summary", {}).get("evidence", card.get("why"))
    return result
