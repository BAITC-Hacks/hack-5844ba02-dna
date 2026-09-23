from fastapi import HTTPException

from api.main import CommonRequest, get_common, get_ego, get_graph, get_node, get_node_card, get_path, get_resilience, get_summary, get_top, health, reload_data, search


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


def test_node_card_has_next_steps_and_string_gid():
    gid = get_graph()["nodes"][0]["id"]
    card = get_node_card(gid)
    assert card["gid"] == gid
    assert isinstance(card["next_steps"], list)
    assert "flows" in card and "connections" in card


def test_summary_and_resilience_are_available():
    assert isinstance(get_summary(), dict)
    assert isinstance(get_resilience(), dict)


def test_ego_path_common_keep_gid_strings():
    graph = get_graph()
    first, second = graph["nodes"][0]["id"], graph["nodes"][1]["id"]
    ego = get_ego(first, k=1, direction="both", max_nodes=10)
    assert ego["center"] == first
    assert all(isinstance(node["id"], str) for node in ego["nodes"])
    path = get_path(first, second)
    assert path["gids"][0] == first and path["gids"][-1] == second
    common = get_common(CommonRequest(gids=[first, second]))
    assert all(isinstance(gid, str) for gid in common["common_receivers"] + common["common_senders"])
