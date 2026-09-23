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
OUT = Path(os.getenv("OUT_DIR", str(ROOT / "out"))).expanduser().resolve()
DATA = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).expanduser().resolve()
WEB = ROOT / "web"

API_DESCRIPTION = """
API аналитического инструмента **«Граф денег»**.

Сервис читает результаты локального пайплайна из `out/` и предоставляет:

* поиск и просмотр направленного графа переводов;
* объяснимые карточки узлов, приоритеты и кластеры;
* ego-сети, пути, общих контрагентов, циклы и устойчивость;
* необязательный AI-ассистент, основанный только на фактах графа.

Все `gid` в HTTP API передаются **строками**: значения порядка `1e17` нельзя
безопасно хранить как JavaScript `Number`. Аналитические выводы являются
гипотезами для проверки, а не утверждениями о виновности.
"""

OPENAPI_TAGS = [
    {"name": "System", "description": "Готовность сервиса и управление локальным пайплайном."},
    {"name": "Graph", "description": "Граф переводов, поиск узлов, связи и маршруты."},
    {"name": "Analytics", "description": "Рейтинг, кластеры, циклы, устойчивость и сводка."},
    {"name": "Cards", "description": "Детерминированные карточки и следующие шаги проверки."},
    {"name": "Assistant", "description": "Необязательный AI-ассистент OpenAI/NVIDIA с опорой на инструменты графа."},
]

app = FastAPI(
    title="Money Graph API",
    summary="Explainable AML transaction-network analytics",
    description=API_DESCRIPTION,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=OPENAPI_TAGS,
    swagger_ui_parameters={
        "deepLinking": True,
        "displayRequestDuration": True,
        "filter": True,
        "persistAuthorization": True,
    },
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/web", StaticFiles(directory=WEB), name="web-legacy")

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


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/health", tags=["System"], summary="Проверить готовность сервиса")
def health() -> dict[str, Any]:
    available, provider = llm_status()
    return {"status": "ok", "out_loaded": store.loaded, "llm_available": available, "provider": provider}


@app.get("/api/summary", tags=["Analytics"], summary="Получить сводку последнего расчёта")
def get_summary() -> dict[str, Any]:
    return _service_call(lambda: (store.require_loaded(), store.summary)[1])


@app.get("/api/graph", tags=["Graph"], summary="Получить граф для визуализации")
def get_graph(min_kzt: Annotated[float, Query(ge=0)] = 0) -> dict[str, Any]:
    return _service_call(store.graph_payload, float(min_kzt))


@app.get("/api/search", tags=["Graph"], summary="Найти gid по префиксу или суффиксу")
def search(q: Annotated[str, Query(max_length=80)] = "") -> list[dict[str, Any]]:
    return _service_call(store.search, q)


@app.get(
    "/api/node/{gid}",
    tags=["Graph"],
    summary="Получить узел и его переводы",
    responses={404: {"description": "gid не найден"}, 503: {"description": "Артефакты пайплайна недоступны"}},
)
def get_node(gid: str) -> dict[str, Any]:
    return _node_call(store.node, str(gid))


@app.get("/api/top", tags=["Analytics"], summary="Получить приоритетный список узлов")
def get_top(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    role: str | None = None,
    cluster: int | None = None,
    exclude_seed: bool = False,
) -> list[dict[str, Any]]:
    return _service_call(store.top_nodes, limit, role, cluster, exclude_seed)


@app.get("/api/clusters", tags=["Analytics"], summary="Получить список кластеров")
def get_clusters() -> list[dict[str, Any]]:
    def payload() -> list[dict[str, Any]]:
        store.require_loaded()
        rows = []
        for raw in store.clusters:
            row = dict(raw)
            row.setdefault("id", row.get("cluster_id"))
            row.setdefault("size", row.get("n_nodes"))
            row.setdefault("seed_count", row.get("n_seed"))
            row.setdefault("turnover_kzt", row.get("sum_kzt_internal"))
            row.setdefault("roles", row.get("role_counts") or {})
            if isinstance(row.get("top_gids"), str):
                row["top_gids"] = [gid for gid in row["top_gids"].split(";") if gid]
            rows.append(row)
        return rows

    return _service_call(payload)


@app.get("/api/cluster/{cluster_id}", tags=["Analytics"], summary="Получить детали кластера")
def get_cluster(cluster_id: int) -> dict[str, Any]:
    try:
        return _service_call(store.cluster, cluster_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"cluster {cluster_id} не найден") from error


@app.get("/api/resilience", tags=["Analytics"], summary="Получить кривые устойчивости сети")
def get_resilience() -> dict[str, Any]:
    return _service_call(store.resilience_payload)


@app.get("/api/cycles", tags=["Analytics"], summary="Получить найденные циклы переводов")
def get_cycles(gid: str | None = None) -> list[list[str]]:
    return _service_call(store.cycles_for, str(gid) if gid is not None else None)


@app.post("/api/reload", tags=["System"], summary="Перечитать артефакты из out/")
def reload_endpoint() -> dict[str, Any]:
    reload_data()
    if not store.loaded:
        raise HTTPException(status_code=503, detail=store.error)
    return {"ok": True, "nodes": len(store.nodes_by_id), "edges": store.graph.number_of_edges()}


@app.post("/api/pipeline/run", tags=["System"], summary="Запустить локальный пайплайн и перечитать результат")
def run_pipeline() -> dict[str, Any]:
    started = time.perf_counter()
    command = [sys.executable, "-m", "pipeline", "--data", str(DATA), "--out", str(OUT)]
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
    elapsed_sec = round(time.perf_counter() - started, 3)
    return {"ok": True, "elapsed_sec": elapsed_sec, "duration_ms": round(elapsed_sec * 1000), "roles": roles}


@app.get("/api/node/{gid}/card", tags=["Cards"], summary="Получить объяснимую карточку узла")
def get_node_card(gid: str) -> dict[str, Any]:
    node = get_node(gid)
    card = build_card(str(gid), node, node["incoming"], node["outgoing"], store.nodes_by_id)
    card["llm_available"] = llm_status()[0]
    return card


@app.get("/api/node/{gid}/ego", tags=["Graph"], summary="Построить ограниченную ego-сеть")
def get_ego(
    gid: str,
    k: Annotated[int, Query(ge=1, le=3)] = 1,
    direction: str = "both",
    max_nodes: Annotated[int, Query(ge=1, le=300)] = 300,
) -> dict[str, Any]:
    if direction not in {"up", "down", "both"}:
        raise HTTPException(status_code=400, detail="direction must be up, down, or both")
    return _node_call(store.ego, str(gid), k, direction, max_nodes)


@app.get("/api/path", tags=["Graph"], summary="Найти кратчайший направленный путь")
def get_path(src: str, dst: str) -> dict[str, Any]:
    try:
        return _node_call(store.shortest_path, str(src), str(dst))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/common", tags=["Graph"], summary="Найти общих отправителей и получателей")
def get_common(request: CommonRequest) -> dict[str, Any]:
    return _node_call(store.common_counterparties, [str(gid) for gid in request.gids])


@app.post(
    "/api/assistant",
    tags=["Assistant"],
    summary="Задать вопрос AI-ассистенту",
    responses={503: {"description": "LLM-провайдер не настроен или недоступен"}},
)
def ask_assistant(request: AssistantRequest) -> dict[str, Any]:
    try:
        return assistant.answer(request.question, request.history)
    except assistant.llm.LLMUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post(
    "/api/node/{gid}/card/llm",
    tags=["Assistant"],
    summary="Сформировать связное объяснение карточки",
    responses={404: {"description": "gid не найден"}, 503: {"description": "LLM-провайдер не настроен или недоступен"}},
)
def explain_card(gid: str) -> dict[str, Any]:
    card = get_node_card(gid)
    try:
        result = assistant.answer_card(card)
    except assistant.llm.LLMUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    result["evidence"] = card.get("summary", {}).get("evidence", card.get("why"))
    return result


# Keep this mount last: API and documentation routes above take precedence, while
# root-relative frontend assets such as /style.css and /js/api.js remain available.
app.mount("/", StaticFiles(directory=WEB, html=True), name="frontend")
