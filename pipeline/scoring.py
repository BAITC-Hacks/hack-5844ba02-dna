"""Приоритизация узлов только по MUST-HAVE компонентам."""
import json
import pandas as pd


def _rank(values: pd.Series) -> pd.Series:
    return values.fillna(0).rank(method="average", pct=True)


def score_nodes(features: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Взвешивает перцентильные ранги и сохраняет прозрачный breakdown."""
    result = features.copy()
    weights = cfg["scoring"]["must_have_weights"]
    role_values = result.role.map(cfg["scoring"]["role_weights"]).fillna(0.0)
    components = {
        "n_seed_upstream": _rank(result.n_seed_upstream),
        "role": _rank(role_values),
        "betweenness": _rank(result.betweenness),
        "degree": _rank(result.in_deg + result.out_deg),
    }
    contributions = {name: components[name] * weights[name] for name in weights}
    raw = sum(contributions.values())
    raw = raw * result.is_seed.map(lambda is_seed: cfg["scoring"]["seed_multiplier"] if is_seed else 1.0)
    result["priority_score"] = raw / raw.max() if raw.max() else 0.0
    result["score_breakdown"] = [json.dumps({key: round(float(values.iloc[i]), 3) for key, values in contributions.items()}, ensure_ascii=False, sort_keys=True) for i in range(len(result))]
    return result


def top_nodes(features: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Выдаёт top-N c тремя главными вкладами и исходными значениями."""
    weight = cfg["scoring"]["must_have_weights"]
    ordered = features.sort_values(["priority_score", "gid"], ascending=[False, True]).head(cfg["scoring"]["top_n"]).copy()
    rows = []
    for rank, row in enumerate(ordered.itertuples(index=False), 1):
        values = {"n_seed_upstream": row.n_seed_upstream, "role": row.role, "betweenness": row.betweenness, "degree": row.in_deg + row.out_deg}
        breakdown = json.loads(row.score_breakdown)
        factors = sorted(breakdown, key=breakdown.get, reverse=True)[:3]
        human = ", ".join(f"{name}: {values[name]}" for name in factors)
        rows.append({"rank": rank, "gid": int(row.gid), "role": row.role, "priority_score": row.priority_score, "why": f"{row.evidence} Главные факторы: {human}"[:500]})
    return pd.DataFrame(rows)
