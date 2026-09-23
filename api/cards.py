"""Deterministic analyst cards derived only from graph facts."""

from __future__ import annotations

from typing import Any


# Review thresholds agreed for deterministic next-step recommendations.
EXTERNAL_FUNDING_PASS_RATIO = 1.2
LARGE_INFLOW_KZT = 1_000_000
NEAR_THRESHOLD_SHARE = 0.3
TOP_COUNTERPARTIES = 3

FLAG_LABELS = {
    "fast_pass": "быстрый транзит средств",
    "sync_in": "синхронные переводы от нескольких плательщиков",
    "near_threshold": "переводы рядом с порогом выгрузки",
    "cycles": "участие в возвратных потоках",
    "external_funding": "возможны источники вне выборки",
    "bridge": "мост между сообществами",
    "S1": "координационный сигнал S1: переводы в сторону seed",
    "S2": "координационный сигнал S2: высокий входящий и исходящий охват",
    "S3": "координационный сигнал S3: связи с узлами сбора или распределения",
}


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _flag_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if not value:
        return []
    text = str(value)
    separator = ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]


def _top(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: (-_number(row.get("sum_kzt")), str(row.get("gid", ""))))
    return ordered[:TOP_COUNTERPARTIES]


def _next_steps(
    node: dict[str, Any],
    incoming: list[dict[str, Any]],
    outgoing: list[dict[str, Any]],
    node_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    role = str(node.get("role") or "")
    pass_ratio = _number(node.get("pass_ratio"))
    near_share = _number(node.get("near_threshold_share"))
    neighbors = incoming + outgoing
    has_frontier_neighbor = any(
        str(node_lookup.get(str(edge.get("gid")), {}).get("role") or "") == "frontier"
        for edge in neighbors
    )
    steps: list[str] = []
    if role == "frontier" or has_frontier_neighbor:
        steps.append("продлить обход от этого узла на 1–2 колена")
    if pass_ratio > EXTERNAL_FUNDING_PASS_RATIO:
        steps.append("запросить входящие переводы из-за пределов выборки")
    if role in {"consolidator", "terminal"} and _number(node.get("in_kzt")) >= LARGE_INFLOW_KZT:
        steps.append("запросить межбанковские переводы и снятия наличных")
    if near_share >= NEAR_THRESHOLD_SHARE:
        steps.append("запросить транзакции < 5 000 KZT (возможно дробление)")
    if role == "coordinator":
        steps.append("приоритетно: запрос в правоохранительные органы по связям с seed")
    if _number(node.get("n_cycles")) > 0:
        steps.append("проверить возвратные потоки")
    return steps or ["сопоставить гипотезу с исходными транзакциями и соседями узла"]


def build_card(
    gid: str,
    node: dict[str, Any],
    incoming: list[dict[str, Any]],
    outgoing: list[dict[str, Any]],
    node_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build an explainable review card without an LLM."""
    role = str(node.get("role") or "")
    evidence = str(node.get("evidence") or "—")
    pass_ratio = node.get("pass_ratio")
    raw_flags = _flag_values(node.get("flags"))
    human_flags = [FLAG_LABELS.get(flag, flag) for flag in raw_flags]
    if _number(pass_ratio) > EXTERNAL_FUNDING_PASS_RATIO:
        human_flags.append("возможны источники вне выборки")
    next_steps = _next_steps(node, incoming, outgoing, node_lookup)
    attention = "; ".join(human_flags) if human_flags else "Интерпретировать роль как гипотезу для проверки."
    top_counterparties = {"incoming": _top(incoming), "outgoing": _top(outgoing)}
    flows = {
        "in_kzt": node.get("in_kzt"),
        "out_kzt": node.get("out_kzt"),
        "seed_flow_kzt": node.get("seed_flow_kzt"),
        "pass_ratio": pass_ratio,
    }
    return {
        "gid": str(gid),
        "summary": {"role": role, "evidence": evidence},
        "flows": flows,
        "top_counterparties": top_counterparties,
        "flags": sorted(set(human_flags)),
        "attention": attention,
        "next_steps": next_steps,
        "score_breakdown": node.get("score_breakdown") or {},
        "p_terminal": node.get("p_terminal"),
        # Backward-compatible aliases for the current frontend.
        "role": role,
        "why": evidence,
        "connections": top_counterparties,
    }
