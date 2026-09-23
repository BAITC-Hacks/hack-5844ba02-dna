"""Deterministic analyst cards derived only from loaded graph facts."""

from typing import Any


def _money(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_card(gid: str, node: dict[str, Any], incoming: list[dict[str, Any]], outgoing: list[dict[str, Any]], node_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build a review card and deterministic next steps for one node."""
    role = str(node.get("role", ""))
    pass_ratio = _money(node.get("pass_ratio"))
    near_threshold = _money(node.get("near_threshold_share"))
    frontier_neighbor = any(str(node_lookup.get(str(edge["gid"]), {}).get("role", "")) == "frontier" for edge in incoming + outgoing)
    steps: list[str] = []
    if role == "frontier" or frontier_neighbor:
        steps.append("Продлить обход от этого узла на 1–2 колена")
    if pass_ratio > 1.2:
        steps.append("Запросить входящие переводы из-за пределов выборки")
    if role in {"consolidator", "terminal"} and max(_money(node.get("in_kzt")), _money(node.get("out_kzt"))) >= 1_000_000:
        steps.append("Запросить межбанковские переводы и снятия наличных")
    if near_threshold >= 0.2:
        steps.append("Запросить транзакции < 5 000 KZT (возможно дробление)")
    if role == "coordinator":
        steps.append("Приоритетно: запрос в правоохранительные органы по связям с seed")
    flags = [flag for flag in str(node.get("flags", "")).split(",") if flag]
    if pass_ratio > 1.2:
        flags.append("источники вне выборки возможны")
    return {
        "gid": str(gid), "role": role, "why": str(node.get("evidence", "—")),
        "flows": {"in_kzt": node.get("in_kzt", "—"), "out_kzt": node.get("out_kzt", "—"), "seed_flow_kzt": node.get("seed_flow_kzt", "—")},
        "connections": {"incoming": sorted(incoming, key=lambda row: _money(row.get("sum_kzt")), reverse=True)[:10], "outgoing": sorted(outgoing, key=lambda row: _money(row.get("sum_kzt")), reverse=True)[:10]},
        "flags": sorted(set(flags)), "attention": "Есть источники вне выборки." if pass_ratio > 1.2 else "Интерпретировать как гипотезу для проверки.",
        "next_steps": steps or ["Сопоставить узел с транзакциями и соседями в исходной выборке."],
        "score_breakdown": node.get("score_breakdown", {}),
        "p_terminal": node.get("p_terminal", "—"),
    }
