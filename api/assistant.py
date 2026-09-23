"""Tool-grounded assistant for analyst questions."""

import json
import re
from typing import Any, Callable

from . import llm

GID_RE = re.compile(r"\[gid:([0-9]+)\]")


def tool_specs() -> list[dict[str, Any]]:
    def fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {"type": "function", "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": properties, "required": required}}}
    return [
        fn("search_nodes", "Search nodes by GID prefix or suffix.", {"q": {"type": "string"}}, ["q"]),
        fn("get_node", "Get facts and flows for one node.", {"gid": {"type": "string"}}, ["gid"]),
        fn("get_neighbors", "Get incoming or outgoing neighbors for a node.", {"gid": {"type": "string"}, "direction": {"type": "string", "enum": ["up", "down", "both"]}}, ["gid", "direction"]),
        fn("common_counterparties", "Find common senders and receivers.", {"gids": {"type": "array", "items": {"type": "string"}}}, ["gids"]),
        fn("shortest_path", "Find a directed shortest path.", {"src": {"type": "string"}, "dst": {"type": "string"}}, ["src", "dst"]),
        fn("get_cluster", "Get one cluster row.", {"cluster_id": {"type": "integer"}}, ["cluster_id"]),
        fn("top_nodes", "Get ranked nodes, optionally filtered by role or cluster.", {"role": {"type": "string"}, "cluster": {"type": "integer"}, "limit": {"type": "integer"}}, []),
    ]


def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    from . import main
    if name == "search_nodes":
        return main.search(str(arguments.get("q", "")))
    if name == "get_node":
        return main.get_node(str(arguments["gid"]))
    if name == "get_neighbors":
        node = main.get_node(str(arguments["gid"]))
        direction = arguments.get("direction", "both")
        if direction == "up":
            return node["incoming"]
        if direction == "down":
            return node["outgoing"]
        return {"incoming": node["incoming"], "outgoing": node["outgoing"]}
    if name == "common_counterparties":
        return main.get_common(main.CommonRequest(gids=[str(gid) for gid in arguments["gids"]]))
    if name == "shortest_path":
        return main.get_path(str(arguments["src"]), str(arguments["dst"]))
    if name == "get_cluster":
        cluster = str(arguments["cluster_id"])
        return [row for row in main.clusters_data if str(row.get("cluster_id")) == cluster]
    if name == "top_nodes":
        rows = main.top_data
        if arguments.get("role"):
            rows = [row for row in rows if row.get("role") == arguments["role"]]
        if arguments.get("cluster") is not None:
            rows = [row for row in rows if str(row.get("cluster_id")) == str(arguments["cluster"])]
        return rows[: min(int(arguments.get("limit", 20)), 50)]
    raise ValueError(f"Unknown tool: {name}")


def answer(question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Answer using only graph-tool facts, with at most six tool rounds."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": "Use only facts returned by tools. Do not invent numbers. Write GIDs fully as [gid:...] and formulate conclusions as hypotheses for review. Answer in the language of the question."}]
    messages.extend((history or [])[-10:])
    messages.append({"role": "user", "content": question})
    calls: list[dict[str, Any]] = []
    for _ in range(6):
        response = llm.complete(messages, tool_specs())
        message = response.choices[0].message
        calls.extend({"name": call.function.name, "arguments": call.function.arguments} for call in (message.tool_calls or []))
        if not message.tool_calls:
            answer_text = message.content or ""
            from . import main
            cited = [gid for gid in GID_RE.findall(answer_text) if gid in main.nodes_by_id]
            return {"answer": answer_text, "cited_gids": cited, "tool_calls": calls}
        messages.append(message.model_dump(exclude_none=True))
        for call in message.tool_calls:
            try:
                result = execute_tool(call.function.name, json.loads(call.function.arguments or "{}"))
            except Exception as error:
                result = {"error": str(error)}
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)})
    return {"answer": "Не удалось завершить анализ за шесть шагов инструментов.", "cited_gids": [], "tool_calls": calls}
