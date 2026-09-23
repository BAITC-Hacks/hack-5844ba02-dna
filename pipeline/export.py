"""Запись контрактных CSV, Parquet и JSON файлов MUST-HAVE."""
import json
import logging
import time
from pathlib import Path
import pandas as pd


LOG = logging.getLogger(__name__)


def export_all(features: pd.DataFrame, edges: pd.DataFrame, clusters: pd.DataFrame, top: pd.DataFrame, layout: pd.DataFrame, cfg: dict, stage_seconds: dict[str, float], started: float) -> None:
    """Сериализует все семь контрактных файлов, gid в JSON всегда строкой."""
    export_started = time.perf_counter()
    out = Path(cfg["_out"]); out.mkdir(parents=True, exist_ok=True)
    result = features.merge(layout, on="gid", how="left")
    columns = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence", "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx", "out_tx", "pass_ratio", "n_seed_upstream", "betweenness", "flags", "score_breakdown"]
    result[columns].to_csv(out / "nodes_roles.csv", index=False)
    clusters.to_csv(out / "clusters.csv", index=False)
    top.to_csv(out / "top_nodes.csv", index=False)
    features.to_parquet(out / "features.parquet", index=False)
    graph = {"nodes": [{"id": str(int(row.gid)), "role": row.role, "cluster": int(row.cluster_id), "priority": float(row.priority_score), "role_score": float(row.role_score), "depth": int(row.depth), "is_seed": bool(row.is_seed), "x": float(row.x), "y": float(row.y), "in_kzt": float(row.in_kzt), "out_kzt": float(row.out_kzt)} for row in result.itertuples(index=False)], "edges": [{"source": str(int(row.src)), "target": str(int(row.dst)), "sum_kzt": float(row.sum_kzt), "n_tx": int(row.n_tx)} for row in edges.itertuples(index=False)]}
    (out / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    thresholds = {key: value for key, value in cfg.items() if key != "_out"}
    stage_seconds["export"] = time.perf_counter() - export_started
    LOG.info("Этап export: %.3f с", stage_seconds["export"])
    summary = {"role_counts": {str(key): int(value) for key, value in features.role.value_counts().sort_index().items()}, "n_clusters": int((clusters.cluster_id != cfg["clusters"]["isolated_cluster_id"]).sum()), "elapsed_seconds": time.perf_counter() - started, "stage_seconds": stage_seconds, "thresholds": thresholds, "frontier": {"auc": None}}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "resilience.json").write_text(json.dumps({"n_removed": []}), encoding="utf-8")
