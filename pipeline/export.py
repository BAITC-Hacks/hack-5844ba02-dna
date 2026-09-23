"""Запись контрактных CSV, Parquet и JSON файлов MUST-HAVE."""
from pathlib import Path
import json
import time
import pandas as pd


def export_all(features: pd.DataFrame, edges: pd.DataFrame, clusters: pd.DataFrame, top: pd.DataFrame, layout: pd.DataFrame, cfg: dict, elapsed: float) -> None:
    """Сериализует все семь контрактных файлов, gid в JSON всегда строкой."""
    out = Path(cfg["_out"]); out.mkdir(parents=True, exist_ok=True)
    result = features.merge(layout, on="gid", how="left")
    columns = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence", "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "pass_ratio", "n_seed_upstream", "betweenness", "flags", "score_breakdown"]
    result[columns].to_csv(out / "nodes_roles.csv", index=False)
    clusters.to_csv(out / "clusters.csv", index=False)
    top.to_csv(out / "top_nodes.csv", index=False)
    features.to_parquet(out / "features.parquet", index=False)
    graph = {"nodes": [{"id": str(int(row.gid)), "role": row.role, "cluster": int(row.cluster_id), "priority": float(row.priority_score), "role_score": float(row.role_score), "depth": int(row.depth), "is_seed": bool(row.is_seed), "x": float(row.x), "y": float(row.y), "in_kzt": float(row.in_kzt), "out_kzt": float(row.out_kzt)} for row in result.itertuples(index=False)], "edges": [{"source": str(int(row.src)), "target": str(int(row.dst)), "sum_kzt": float(row.sum_kzt), "n_tx": int(row.n_tx)} for row in edges.itertuples(index=False)]}
    (out / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    thresholds = {key: value for key, value in cfg.items() if key != "_out"}
    summary = {"role_counts": {str(key): int(value) for key, value in features.role.value_counts().sort_index().items()}, "n_clusters": int((clusters.cluster_id != cfg["clusters"]["isolated_cluster_id"]).sum()), "elapsed_seconds": elapsed, "thresholds": thresholds, "frontier": {"auc": None}}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "resilience.json").write_text(json.dumps({"n_removed": []}), encoding="utf-8")
