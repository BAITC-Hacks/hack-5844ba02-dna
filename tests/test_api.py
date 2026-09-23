from fastapi import HTTPException

from api.main import get_graph, get_node, get_top, health, reload_data, search


def setup_module():
    import scripts.make_mock_out as mock
    mock.main()
    reload_data()


def test_graph_ids_are_strings():
    payload = get_graph()
    assert payload["nodes"]
    assert all(isinstance(node["id"], str) for node in payload["nodes"])
    assert all(isinstance(edge["source"], str) and isinstance(edge["target"], str) for edge in payload["edges"])


def test_search_by_last_six_digits():
    graph = get_graph()
    gid = graph["nodes"][0]["id"]
    assert any(row["gid"] == gid for row in search(gid[-6:]))


def test_existing_and_missing_node():
    gid = get_graph()["nodes"][0]["id"]
    node = get_node(gid)
    assert node["id"] == gid
    assert isinstance(node["score_breakdown"], dict)
    try:
        get_node("999999999999999999")
    except HTTPException as error:
        assert error.status_code == 404
        assert "was not found" in error.detail
    else:
        raise AssertionError("missing node did not return 404")


def test_top_endpoint():
    assert len(get_top(20)) == 20


def test_health_without_llm_key(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    assert health() == {"status": "ok", "llm_available": False, "provider": "none"}
