"""Приоритизация узлов только по MUST-HAVE компонентам."""
import json
import pandas as pd


def _rank(values: pd.Series) -> pd.Series:
    return values.fillna(0).rank(method="average", pct=True)


def score_nodes(features: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Взвешивает перцентильные ранги и сохраняет прозрачный breakdown."""
    result = features.copy()
    weights = cfg["scoring"]["weights"]
    role_values = result.role.map(cfg["scoring"]["role_weights"]).fillna(0.0)
    components = {
        "seed_flow_kzt": _rank(result.seed_flow_kzt),
        "n_seed_upstream": _rank(result.n_seed_upstream),
        "role": _rank(role_values),
        "betweenness": _rank(result.betweenness),
        "degree": _rank(result.in_deg + result.out_deg),
        "temporal": pd.concat([_rank(result.fast_pass_share), _rank(result.near_threshold_share), _rank(result.n_cycles), result.max_sync_payers.ge(cfg["roles"]["temporal"]["sync_min_payers"]).astype(float)], axis=1).mean(axis=1),
    }
    contributions = {name: components[name] * weights[name] for name in weights}
    raw = sum(contributions.values())
    raw = raw * result.is_seed.map(lambda is_seed: cfg["scoring"]["seed_multiplier"] if is_seed else 1.0)
    result["priority_score"] = raw / raw.max() if raw.max() else 0.0
    result["score_breakdown"] = [json.dumps({key: round(float(values.iloc[i]), 3) for key, values in contributions.items()}, ensure_ascii=False, sort_keys=True) for i in range(len(result))]
    return result


def top_nodes(features: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Выдаёт top-N c тремя главными вкладами и исходными значениями."""
    weight = cfg["scoring"]["weights"]
    ordered = features.sort_values(["priority_score", "gid"], ascending=[False, True]).head(cfg["scoring"]["top_n"]).copy()
    rows = []
    for rank, row in enumerate(ordered.itertuples(index=False), 1):
        values = {"seed_flow_kzt": f"{row.seed_flow_kzt / 1_000_000:.1f} млн", "n_seed_upstream": row.n_seed_upstream, "role": row.role, "betweenness": row.betweenness, "degree": row.in_deg + row.out_deg, "temporal": f"быстрые переводы {row.fast_pass_share:.0%}"}
        breakdown = json.loads(row.score_breakdown)
        factors = sorted(breakdown, key=breakdown.get, reverse=True)[:3]
        human = ", ".join(f"{name}: {values[name]}" for name in factors)
        rows.append({"rank": rank, "gid": int(row.gid), "role": row.role, "priority_score": row.priority_score, "why": f"{row.evidence} Главные факторы: {human}"[:500]})
    return pd.DataFrame(rows)
