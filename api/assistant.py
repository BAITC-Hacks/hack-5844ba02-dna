"""Tool-grounded AI assistant for analyst questions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from . import llm


ROOT = Path(__file__).resolve().parents[1]
GID_RE = re.compile(r"\[gid:([0-9]+)\]")
MAX_TOOL_ROUNDS = 6


def _store():
    from .main import store

    store.require_loaded()
    return store


def _role_rules() -> str:
    config_path = ROOT / "pipeline" / "config.yaml"
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return "Правила ролей недоступны; опирайся только на факты инструментов."
    relevant = {
        "roles": config.get("roles", {}),
        "scoring": config.get("scoring", {}),
        "data_limitations": config.get("data", {}),
    }
    return json.dumps(relevant, ensure_ascii=False, sort_keys=True)


def _system_prompt() -> str:
    return (
        "Ты помощник AML-аналитика. Используй только факты, возвращённые инструментами, и не выдумывай числа. "
        "Полные идентификаторы пиши только как [gid:...]. Все выводы формулируй как гипотезы для проверки, "
        "никогда как обвинения. Отвечай на языке вопроса. Учитывай ограничения исходящих переводов, "
        "порог 5 000 KZT и обрыв обхода на четвёртом колене. "
        f"Текущие правила, пороги и веса из pipeline/config.yaml: {_role_rules()}"
    )


def tool_specs() -> list[dict[str, Any]]:
    def fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        }

    return [
        fn("search_nodes", "Найти узлы по префиксу или суффиксу gid.", {"q": {"type": "string"}}, ["q"]),
        fn("get_node", "Получить факты и потоки одного узла.", {"gid": {"type": "string"}}, ["gid"]),
        fn(
            "get_neighbors",
            "Получить входящих или исходящих соседей узла.",
            {"gid": {"type": "string"}, "direction": {"type": "string", "enum": ["up", "down", "both"]}},
            ["gid", "direction"],
        ),
        fn(
            "common_counterparties",
            "Найти общих отправителей и получателей на одном-двух шагах.",
            {"gids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 20}},
            ["gids"],
        ),
        fn(
            "shortest_path",
            "Найти кратчайший направленный путь.",
            {"src": {"type": "string"}, "dst": {"type": "string"}},
            ["src", "dst"],
        ),
        fn("get_cluster", "Получить состав и внутренние связи кластера.", {"id": {"type": "integer"}}, ["id"]),
        fn(
            "top_nodes",
            "Получить рейтинг с необязательными фильтрами.",
            {"role": {"type": "string"}, "cluster": {"type": "integer"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
            [],
        ),
    ]


def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    store = _store()
    if name == "search_nodes":
        return store.search(str(arguments.get("q", "")))
    if name == "get_node":
        return store.node(str(arguments["gid"]))
    if name == "get_neighbors":
        node = store.node(str(arguments["gid"]))
        direction = arguments.get("direction", "both")
        if direction == "up":
            return node["incoming"]
        if direction == "down":
            return node["outgoing"]
        return {"incoming": node["incoming"], "outgoing": node["outgoing"]}
    if name == "common_counterparties":
        return store.common_counterparties([str(gid) for gid in arguments["gids"]])
    if name == "shortest_path":
        return store.shortest_path(str(arguments["src"]), str(arguments["dst"]))
    if name == "get_cluster":
        return store.cluster(int(arguments["id"]))
    if name == "top_nodes":
        return store.top_nodes(
            min(int(arguments.get("limit", 20)), 50),
            str(arguments["role"]) if arguments.get("role") else None,
            int(arguments["cluster"]) if arguments.get("cluster") is not None else None,
            False,
        )
    raise ValueError(f"Unknown tool: {name}")


def _cited_gids(text: str) -> list[str]:
    existing = _store().nodes_by_id
    return list(dict.fromkeys(gid for gid in GID_RE.findall(text) if gid in existing))


def answer(question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Answer from graph tools, with no more than six tool-call rounds."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt()}]
    messages.extend((history or [])[-10:])
    messages.append({"role": "user", "content": question})
    calls: list[dict[str, Any]] = []
    for _ in range(MAX_TOOL_ROUNDS):
        response = llm.complete(messages, tool_specs())
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            answer_text = message.content or ""
            return {"answer": answer_text, "cited_gids": _cited_gids(answer_text), "tool_calls": calls}
        messages.append(message.model_dump(exclude_none=True))
        for call in tool_calls:
            raw_arguments = call.function.arguments or "{}"
            calls.append({"name": call.function.name, "arguments": raw_arguments})
            try:
                result = execute_tool(call.function.name, json.loads(raw_arguments))
            except Exception as error:
                result = {"error": str(error)}
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)}
            )
    return {
        "answer": "Не удалось завершить анализ за шесть шагов инструментов.",
        "cited_gids": [],
        "tool_calls": calls,
    }


def answer_card(card: dict[str, Any]) -> dict[str, Any]:
    """Turn one deterministic card into prose without accessing extra facts."""
    messages = [
        {
            "role": "system",
            "content": (
                "Составь краткую справку AML-аналитика только по данным карточки пользователя. "
                "Не добавляй числа и факты. Формулируй выводы как гипотезы для проверки и отвечай на языке карточки."
            ),
        },
        {"role": "user", "content": json.dumps(card, ensure_ascii=False)},
    ]
    response = llm.complete(messages)
    text = response.choices[0].message.content or ""
    return {"answer": text, "cited_gids": _cited_gids(text), "tool_calls": []}
