"""Acceptance tests for the FastAPI backend contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.graph_store import GraphStore, StoreUnavailable
from api.main import (
    AssistantRequest,
    CommonRequest,
    ask_assistant,
    get_cluster,
    get_clusters,
    get_common,
    get_cycles,
    get_ego,
    get_graph,
    get_node,
    get_node_card,
    get_path,
    get_resilience,
    get_summary,
    get_top,
    health,
    reload_data,
    search,
    app,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"


def setup_module() -> None:
    required = [OUT / name for name in ("graph.json", "nodes_roles.csv", "clusters.csv", "top_nodes.csv")]
    if not all(path.exists() for path in required):
        import scripts.make_mock_out as mock

        mock.main()
    reload_data()


def _assert_gid_strings(value: Any, key: str | None = None) -> None:
    if key in {"gid", "id", "source", "target", "center", "src", "dst"} and value is not None:
        assert isinstance(value, str), f"{key} must be a string: {value!r}"
    if key in {"gids", "cited_gids"} and isinstance(value, list):
        assert all(isinstance(item, str) for item in value)
    if isinstance(value, dict):
        for child_key, child in value.items():
            _assert_gid_strings(child, child_key)
    elif isinstance(value, list):
        for child in value:
            _assert_gid_strings(child, key)


def test_health_and_summary() -> None:
    payload = health()
    assert payload == {"status": "ok", "out_loaded": True, "llm_available": False, "provider": None}
    summary = get_summary()
    assert summary["n_nodes"] == len(get_graph()["nodes"])
    assert "n_seed" in summary
    assert summary["nodes"] == summary["n_nodes"]
    assert summary["seeds"] == summary["n_seed"]
    assert summary["roles"] == summary["role_counts"]


def test_openapi_contract_and_swagger_metadata() -> None:
    schema = app.openapi()
    assert schema["info"]["title"] == "Money Graph API"
    assert schema["info"]["version"] == "2.0.0"
    assert {tag["name"] for tag in schema["tags"]} == {"System", "Graph", "Analytics", "Cards", "Assistant"}
    assert "/api/graph" in schema["paths"]
    assert "/api/assistant" in schema["paths"]
    gid_schema = schema["paths"]["/api/node/{gid}"]["get"]["parameters"][0]["schema"]
    assert gid_schema["type"] == "string"


def test_frontend_and_root_relative_assets_are_served() -> None:
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert "TRACE" in client.get("/").text
    assert client.get("/style.css").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/js/api.js").status_code == 200


def test_graph_filter_and_string_identifiers() -> None:
    payload = get_graph()
    assert payload["nodes"] and payload["edges"]
    _assert_gid_strings(payload)
    threshold = max(float(edge["sum_kzt"]) for edge in payload["edges"])
    filtered = get_graph(threshold)
    assert filtered["edges"]
    assert all(float(edge["sum_kzt"]) >= threshold for edge in filtered["edges"])


def test_search_by_last_six_digits() -> None:
    gid = get_graph()["nodes"][0]["id"]
    rows = search(gid[-6:])
    assert any(row["gid"] == gid for row in rows)
    assert all({"gid", "role", "priority_score", "cluster_id"} == set(row) for row in rows)
    _assert_gid_strings(rows)


def test_existing_and_missing_node() -> None:
    gid = get_graph()["nodes"][0]["id"]
    node = get_node(gid)
    assert node["id"] == gid and node["gid"] == gid
    assert isinstance(node["score_breakdown"], dict)
    assert isinstance(node["flags"], list)
    for direction in ("incoming", "outgoing"):
        amounts = [row["sum_kzt"] for row in node[direction]]
        assert amounts == sorted(amounts, reverse=True)
    _assert_gid_strings(node)
    with pytest.raises(HTTPException) as captured:
        get_node("999999999999999999")
    assert captured.value.status_code == 404
    assert captured.value.detail == "gid 999999999999999999 не найден"


def test_card_has_deterministic_review_sections() -> None:
    gid = get_graph()["nodes"][0]["id"]
    card = get_node_card(gid)
    assert card["gid"] == gid
    assert set(card["summary"]) == {"role", "evidence"}
    assert {"in_kzt", "out_kzt", "seed_flow_kzt", "pass_ratio"} == set(card["flows"])
    assert set(card["top_counterparties"]) == {"incoming", "outgoing"}
    assert all(len(card["top_counterparties"][key]) <= 3 for key in ("incoming", "outgoing"))
    assert isinstance(card["next_steps"], list) and card["next_steps"]
    assert card["role"] == card["summary"]["role"]
    assert card["evidence"] == card["summary"]["evidence"]
    assert card["metrics"]["in_kzt"] == card["flows"]["in_kzt"]
    assert card["payers"] == card["top_counterparties"]["incoming"]
    assert card["payees"] == card["top_counterparties"]["outgoing"]
    _assert_gid_strings(card)


def test_ego_path_and_common() -> None:
    edge = get_graph()["edges"][0]
    src, dst = edge["source"], edge["target"]
    ego = get_ego(src, k=1, direction="both", max_nodes=10)
    assert ego["center"] == src and len(ego["nodes"]) <= 10
    path = get_path(src, dst)
    assert path["gids"] == [src, dst]
    common = get_common(CommonRequest(gids=[src, dst]))
    for key in ("common_receivers", "common_senders"):
        assert all({"gid", "role", "sum_kzt", "hops"} == set(row) for row in common[key])
        assert all(row["hops"] in {1, 2} for row in common[key])
    _assert_gid_strings(ego)
    _assert_gid_strings(path)
    _assert_gid_strings(common)


def test_top_filters_and_cluster_detail() -> None:
    first = get_top(1)[0]
    node = get_node(first["gid"])
    role = first["role"]
    cluster_id = int(node.get("cluster_id", node.get("cluster")))
    filtered = get_top(50, role=role, cluster=cluster_id, exclude_seed=False)
    assert filtered
    assert all(row["role"] == role and int(row["cluster_id"]) == cluster_id for row in filtered)
    assert all(isinstance(row["gid"], str) for row in get_top(50, exclude_seed=True))
    cluster = get_cluster(cluster_id)
    assert cluster["nodes"] and "role_counts" in cluster and "internal_edges" in cluster
    cluster_rows = get_clusters()
    assert any(str(row["cluster_id"]) == str(cluster_id) for row in cluster_rows)
    assert all({"id", "size", "seed_count", "turnover_kzt", "roles"}.issubset(row) for row in cluster_rows)
    _assert_gid_strings(first)
    _assert_gid_strings(cluster)


def test_resilience_returns_every_strategy() -> None:
    raw_path = OUT / "resilience.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else {}
    expected = {
        key for key, value in raw.items()
        if isinstance(value, dict) and {"lwcc_size", "seed_reachable"}.issubset(value)
    }
    payload = get_resilience()
    assert set(payload["strategies"]) == expected
    assert payload["removed"] == payload["n_removed"]
    assert payload["priority"] == payload["by_priority"]
    assert payload["degree"] == payload["by_degree"]


def test_cycles_filter_and_string_gids() -> None:
    cycles = get_cycles()
    assert all(isinstance(gid, str) for cycle in cycles for gid in cycle)
    if cycles:
        gid = cycles[0][0]
        assert all(gid in cycle for cycle in get_cycles(gid))


def test_assistant_without_key_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(HTTPException) as captured:
        ask_assistant(AssistantRequest(question="Кто требует проверки?"))
    assert captured.value.status_code == 503


def test_empty_store_is_nonfatal(tmp_path: Path) -> None:
    empty = GraphStore(tmp_path)
    assert not empty.loaded and "missing" in str(empty.error)
    with pytest.raises(StoreUnavailable):
        empty.graph_payload()
