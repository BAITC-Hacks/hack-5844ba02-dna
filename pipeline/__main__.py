"""CLI и оркестрация MUST-HAVE этапа."""
import argparse
import logging
from pathlib import Path
import time
import yaml

from .clusters import cluster_nodes, renumber_and_describe
from .export import export_all
from .features import basic_features, enrich_features
from .frontier import add_frontier_probability
from .layout import make_layout
from .load import build_graph, load, sanity_check
from .roles import apply_coordinators, assign_base_roles
from .resilience import calculate_resilience
from .scoring import score_nodes, top_nodes


def _run_stage(stage_seconds: dict[str, float], name: str, function, *args):
    """Выполняет один этап и записывает его длительность в секундах."""
    stage_started = time.perf_counter()
    value = function(*args)
    stage_seconds[name] = time.perf_counter() - stage_started
    logging.getLogger(__name__).info("Этап %s: %.3f с", name, stage_seconds[name])
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    started = time.perf_counter()
    with (Path(__file__).parent / "config.yaml").open(encoding="utf-8") as stream: cfg = yaml.safe_load(stream)
    cfg["_out"] = str(args.out)
    stage_seconds: dict[str, float] = {}
    edges, nodes, transactions = _run_stage(stage_seconds, "load", load, args.data)
    _run_stage(stage_seconds, "sanity_check", sanity_check, edges, nodes, transactions)
    graph = _run_stage(stage_seconds, "build_graph", build_graph, edges, nodes)
    features = _run_stage(stage_seconds, "basic_features", basic_features, graph, nodes)
    features = _run_stage(stage_seconds, "enrich_features", enrich_features, graph, features, cfg)
    features, frontier = _run_stage(stage_seconds, "frontier", add_frontier_probability, features, transactions, cfg)
    features = _run_stage(stage_seconds, "assign_base_roles", assign_base_roles, features, cfg)
    features = _run_stage(stage_seconds, "apply_coordinators", apply_coordinators, features, graph, cfg)
    features = _run_stage(stage_seconds, "cluster_nodes", cluster_nodes, graph, features, cfg)
    features = _run_stage(stage_seconds, "score_nodes", score_nodes, features, cfg)
    features, clusters = _run_stage(stage_seconds, "renumber_and_describe", renumber_and_describe, features, edges, cfg)
    layout = _run_stage(stage_seconds, "layout", make_layout, graph, cfg)
    resilience = _run_stage(stage_seconds, "resilience", calculate_resilience, graph, features, cfg)
    top = _run_stage(stage_seconds, "top_nodes", top_nodes, features, cfg)
    export_all(features, edges, clusters, top, layout, cfg, stage_seconds, started, frontier, resilience)
    elapsed = time.perf_counter() - started
    print("Роли:", features.role.value_counts().sort_index().to_dict())
    print("Кластеров:", int((clusters.cluster_id != cfg["clusters"]["isolated_cluster_id"]).sum()))
    n20 = resilience["n_removed"].index(20) if 20 in resilience["n_removed"] else -1
    if n20 >= 0:
        print(f"При удалении топ-20: lwcc {resilience['by_priority']['lwcc_size'][n20]} (по степени {resilience['by_degree']['lwcc_size'][n20]}, случайно {resilience['random']['lwcc_size'][n20]:.1f})")
    print(top.head(10)[["gid", "role", "priority_score", "why"]].to_string(index=False))
    print(f"Время: {elapsed:.2f} с")


if __name__ == "__main__":
    main()
