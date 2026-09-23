"""FastAPI read-only viewer API for the money graph."""

import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import networkx as nx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .cards import build_card

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
WEB = ROOT / "web"
app = FastAPI(title="Money Graph Viewer")
app.mount("/web", StaticFiles(directory=WEB), name="web")

graph_data: dict[str, Any] = {"nodes": [], "edges": []}
nodes_by_id: dict[str, dict[str, Any]] = {}
edges_by_node: dict[str, list[dict[str, Any]]] = {}
clusters_data: list[dict[str, Any]] = []
top_data: list[dict[str, Any]] = []
summary_data: dict[str, Any] = {}
resilience_data: dict[str, Any] = {}
graph = nx.DiGraph()


def parse_value(value: str) -> Any:
    if value == "":
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def read_csv(name: str) -> list[dict[str, Any]]:
    path = OUT / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [{key: parse_value(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def reload_data() -> None:
    global graph_data, nodes_by_id, edges_by_node, clusters_data, top_data, summary_data, resilience_data, graph
    graph_path = OUT / "graph.json"
    graph_data = json.loads(graph_path.read_text(encoding="utf-8")) if graph_path.exists() else {"nodes": [], "edges": []}
    graph_data["nodes"] = [{**node, "id": str(node["id"])} for node in graph_data.get("nodes", [])]
    graph_data["edges"] = [{**edge, "source": str(edge["source"]), "target": str(edge["target"])} for edge in graph_data.get("edges", [])]
    csv_nodes = {str(row["gid"]): row for row in read_csv("nodes_roles.csv") if row.get("gid")}
    nodes_by_id = {str(node["id"]): {**csv_nodes.get(str(node["id"]), {}), **node} for node in graph_data["nodes"]}
    edges_by_node = {gid: [] for gid in nodes_by_id}
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes_by_id)
    for edge in graph_data["edges"]:
        graph.add_edge(edge["source"], edge["target"], **edge)
        edges_by_node.setdefault(edge["source"], []).append({"gid": edge["target"], "role": nodes_by_id.get(edge["target"], {}).get("role", ""), "sum_kzt": edge.get("sum_kzt", 0), "n_tx": edge.get("n_tx", 0)})
        edges_by_node.setdefault(edge["target"], []).append({"gid": edge["source"], "role": nodes_by_id.get(edge["source"], {}).get("role", ""), "sum_kzt": edge.get("sum_kzt", 0), "n_tx": edge.get("n_tx", 0)})
    clusters_data = read_csv("clusters.csv")
    top_data = read_csv("top_nodes.csv")
    summary_path = OUT / "summary.json"
    resilience_path = OUT / "resilience.json"
    summary_data = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    resilience_data = json.loads(resilience_path.read_text(encoding="utf-8")) if resilience_path.exists() else {}


def llm_status() -> tuple[bool, str]:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY")), provider
    if provider == "nvidia":
        return bool(os.getenv("NVIDIA_API_KEY")), provider
    return False, provider or "none"


reload_data()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    available, provider = llm_status()
    return {"status": "ok", "llm_available": available, "provider": provider}


@app.get("/api/graph")
def get_graph() -> dict[str, Any]:
    return graph_data


@app.get("/api/search")
def search(q: str = Query(default="", max_length=80)) -> list[dict[str, Any]]:
    needle = str(q).strip()
    if not needle:
        return []
    matches = [node for gid, node in nodes_by_id.items() if gid.startswith(needle) or gid.endswith(needle)]
    return [{"gid": str(node["id"]), "role": node.get("role", ""), "priority": node.get("priority", node.get("priority_score", 0))} for node in matches[:20]]


@app.get("/api/node/{gid}")
def get_node(gid: str) -> dict[str, Any]:
    gid = str(gid)
    if gid not in nodes_by_id:
        raise HTTPException(status_code=404, detail=f"Node {gid} was not found in the loaded graph")
    node = dict(nodes_by_id[gid])
    raw = node.get("score_breakdown", {})
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {"raw": raw}
    node["score_breakdown"] = raw
    node["incoming"] = [{"gid": str(edge["source"]), "role": nodes_by_id.get(str(edge["source"]), {}).get("role", ""), "sum_kzt": edge.get("sum_kzt", 0), "n_tx": edge.get("n_tx", 0)} for edge in graph_data["edges"] if edge["target"] == gid]
    node["outgoing"] = [{"gid": str(edge["target"]), "role": nodes_by_id.get(str(edge["target"]), {}).get("role", ""), "sum_kzt": edge.get("sum_kzt", 0), "n_tx": edge.get("n_tx", 0)} for edge in graph_data["edges"] if edge["source"] == gid]
    return node


@app.get("/api/node/{gid}/card")
def get_node_card(gid: str) -> dict[str, Any]:
    node = get_node(gid)
    return build_card(str(gid), node, node["incoming"], node["outgoing"], nodes_by_id)


@app.get("/api/top")
def get_top(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
    return top_data[:limit]


@app.get("/api/clusters")
def get_clusters() -> list[dict[str, Any]]:
    return clusters_data


@app.get("/api/summary")
def get_summary() -> dict[str, Any]:
    return summary_data


@app.get("/api/resilience")
def get_resilience() -> dict[str, Any]:
    return resilience_data


@app.post("/api/pipeline/run")
def run_pipeline() -> dict[str, Any]:
    command = [sys.executable, "-m", "pipeline", "--data", str(ROOT / "data"), "--out", str(OUT)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr[-2000:] or "Pipeline failed")
    reload_data()
    return {"ok": True, "stdout": result.stdout[-2000:], "summary": summary_data}


@app.post("/api/reload")
def reload_endpoint() -> dict[str, Any]:
    reload_data()
    return {"ok": True, "nodes": len(graph_data["nodes"]), "edges": len(graph_data["edges"])}
