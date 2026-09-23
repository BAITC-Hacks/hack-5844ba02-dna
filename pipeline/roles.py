"""Детерминированные правила ролей и доказательные формулировки."""
import logging
import numpy as np
import pandas as pd


LOG = logging.getLogger(__name__)


def format_kzt(value: float) -> str:
    """Форматирует денежную сумму компактно и воспроизводимо."""
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f} млн"
    return f"{value / 1_000:.0f} тыс."


def _score(value: float, threshold: float, series: pd.Series, cfg: dict) -> float:
    """Линейный score от порога до конфигурируемого верхнего перцентиля."""
    floor, ceiling = cfg["roles"]["score_floor"], cfg["roles"]["score_ceiling"]
    top = float(series.quantile(cfg["roles"]["score_top_percentile"] / 100))
    if top <= threshold:
        return ceiling
    return float(np.clip(floor + (value - threshold) * (ceiling - floor) / (top - threshold), floor, ceiling))


def _trim(text: str, cfg: dict) -> str:
    return text[:cfg["export"]["evidence_max_chars"]]


def _is_distributor(row: pd.Series, cfg: dict) -> bool:
    """Проверяет веерную рассылку с достаточным видимым источником средств."""
    c = cfg["roles"]["distributor"]
    return row.out_deg >= c["min_out_deg"] and (bool(row.is_seed) or row.out_kzt >= c["min_out_in_ratio"] * row.in_kzt)


def _is_consolidator(row: pd.Series, cfg: dict) -> bool:
    """Проверяет накопление от многих плательщиков или нескольких seed."""
    c = cfg["roles"]["consolidator"]
    return ((row.in_deg >= c["min_in_deg"] and row.out_kzt <= c["max_out_in_ratio"] * row.in_kzt) or
            (row.n_seed_upstream >= c["min_seed_upstream"] and row.in_deg >= c["alt_min_in_deg"]))


def _is_transit(row: pd.Series, cfg: dict) -> bool:
    """Проверяет небольшой не-seed узел, почти полностью передающий поток."""
    c = cfg["roles"]["transit"]
    return (not bool(row.is_seed) and c["min_in_deg"] <= row.in_deg <= c["max_in_deg"] and
            c["min_out_deg"] <= row.out_deg <= c["max_out_deg"] and c["min_pass"] <= row.pass_ratio <= c["max_pass"])


def _is_isolated(row: pd.Series) -> bool:
    """Правило a: узел без наблюдаемых входящих и исходящих переводов."""
    return row.in_deg + row.out_deg == 0


def _is_frontier(row: pd.Series, cfg: dict) -> bool:
    """Правило b: обрыв обхода на максимальной глубине без исходящих рёбер."""
    return row.depth == cfg["data"]["max_depth"] and row.out_deg == 0


def _is_terminal(row: pd.Series, cfg: dict) -> bool:
    """Правило f: конечный получатель до глубины обрыва с видимым входом."""
    return (row.out_deg == 0 and row.depth < cfg["data"]["max_depth"] and
            row.in_deg >= cfg["roles"]["terminal"]["min_in_deg"])


def _peripheral_evidence(row: pd.Series) -> str:
    """Правило g: формулирует evidence для узла без более сильного правила."""
    return f"Периферийный узел: {row.in_deg} входящих, {row.out_deg} исходящих, оборот {format_kzt(row.in_kzt + row.out_kzt)}"


def assign_base_roles(features: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Назначает первую сработавшую роль в порядке спецификации MUST-HAVE."""
    result = features.copy()
    roles, scores, evidence, flags = [], [], [], []
    minimum = cfg["data"]["min_tx_kzt"]
    for _, row in result.iterrows():
        local_flags: list[str] = []
        external = pd.notna(row.pass_ratio) and row.pass_ratio > cfg["roles"]["transit"]["max_pass"]
        if _is_isolated(row):
            role, score, ev = "peripheral", cfg["roles"]["peripheral_isolated_score"], f"Нет переводов ≥{minimum} KZT в выгрузке"
        elif _is_frontier(row, cfg):
            role, score, ev = "frontier", cfg["roles"]["frontier"]["score"], f"{cfg['data']['max_depth']}-е колено, исходящие не наблюдались (обрыв обхода), получено {format_kzt(row.in_kzt)}"
        elif _is_distributor(row, cfg):
            role, score = "distributor", _score(row.out_deg, cfg["roles"]["distributor"]["min_out_deg"], result.out_deg, cfg)
            ev = f"Веерная рассылка: {row.out_deg} получателей, отдано {format_kzt(row.out_kzt)}"
        elif _is_consolidator(row, cfg):
            c = cfg["roles"]["consolidator"]
            score = max(_score(row.in_deg, c["min_in_deg"], result.in_deg, cfg), _score(row.n_seed_upstream, c["min_seed_upstream"], result.n_seed_upstream, cfg))
            role, ev = "consolidator", f"Признаки консолидации: {row.in_deg} плательщиков, деньги от {row.n_seed_upstream} seed за ≤2 колена, получено {format_kzt(row.in_kzt)}, дальше ушло {row.pass_ratio * 100 if pd.notna(row.pass_ratio) else 0:.0f}%"
        elif _is_transit(row, cfg):
            c = cfg["roles"]["transit"]
            role, score = "transit", _score(row.pass_ratio, c["min_pass"], result.pass_ratio.dropna(), cfg)
            ev = f"Признаки транзита: получено {format_kzt(row.in_kzt)}, отдано {row.pass_ratio * 100:.0f}%, {row.in_deg}→{row.out_deg} контрагента"
        elif _is_terminal(row, cfg):
            role, score, ev = "terminal", cfg["roles"]["score_floor"], f"Вероятный конечный получатель: {row.in_deg} плательщиков, получено {format_kzt(row.in_kzt)}, исходящих нет"
        else:
            role, score, ev = "peripheral", cfg["roles"]["score_floor"], _peripheral_evidence(row)
        if external:
            local_flags.append("external_funding")
            if role == "peripheral":
                ev += "; есть источники вне выборки"
        roles.append(role); scores.append(score); evidence.append(_trim(ev, cfg)); flags.append(local_flags)
    result["role"], result["role_score"], result["evidence"], result["flags"] = roles, scores, evidence, flags
    return result


def apply_coordinators(features: pd.DataFrame, graph, cfg: dict) -> pd.DataFrame:
    """Вторым проходом помечает узлы с одним из трёх координирующих сигналов."""
    result = features.copy()
    base_roles = result.set_index("gid")["role"].to_dict()
    c = cfg["roles"]["coordinator"]
    hub_payer_counts = {int(gid): sum(base_roles.get(int(source)) in {"consolidator", "distributor"} for source in graph.predecessors(int(gid))) for gid in result["gid"]}
    for index, row in result.iterrows():
        signals: list[str] = []
        if row.pays_seeds >= c["min_pays_seeds"] and row.in_deg >= c["s1_min_in_deg"]: signals.append("S1")
        if row.in_deg >= c["s2_min_in_deg"] and row.out_deg >= c["s2_min_out_deg"]: signals.append("S2")
        hub_payers = hub_payer_counts[int(row.gid)]
        if hub_payers >= c["s3_min_hub_payers"]: signals.append("S3")
        if signals:
            previous = row.role
            result.at[index, "flags"] = list(row["flags"]) + [previous] + signals
            result.at[index, "role"] = "coordinator"
            score_parts = []
            if "S1" in signals: score_parts.extend([_score(row.pays_seeds, c["min_pays_seeds"], result.pays_seeds, cfg), _score(row.in_deg, c["s1_min_in_deg"], result.in_deg, cfg)])
            if "S2" in signals: score_parts.extend([_score(row.in_deg, c["s2_min_in_deg"], result.in_deg, cfg), _score(row.out_deg, c["s2_min_out_deg"], result.out_deg, cfg)])
            if "S3" in signals: score_parts.append(_score(hub_payers, c["s3_min_hub_payers"], pd.Series(hub_payer_counts.values()), cfg))
            result.at[index, "role_score"] = max(score_parts)
            result.at[index, "evidence"] = _trim(f"Кандидат в координирующий узел: {row.in_deg} плательщиков → {row.out_deg} получателей; сигналы {', '.join(signals)}", cfg)
    result["flags"] = result["flags"].map(lambda x: ";".join(x))
    coordinator_count = int(result["role"].eq("coordinator").sum())
    if coordinator_count > c["max_expected"]:
        LOG.warning("Coordinator count %d exceeds configured maximum %d; review S3 sensitivity", coordinator_count, c["max_expected"])
    return result
