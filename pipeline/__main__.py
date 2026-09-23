"""CLI и оркестрация MUST-HAVE этапа."""
import argparse
import logging
from pathlib import Path
import time
import yaml

from .clusters import cluster_nodes, renumber_and_describe
from .export import export_all
from .features import basic_features, enrich_features
from .layout import make_layout
from .load import build_graph, load, sanity_check
from .roles import apply_coordinators, assign_base_roles
from .scoring import score_nodes, top_nodes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    started = time.perf_counter()
    with (Path(__file__).parent / "config.yaml").open(encoding="utf-8") as stream: cfg = yaml.safe_load(stream)
    cfg["_out"] = str(args.out)
    edges, nodes, _ = load(args.data); sanity_check(edges, nodes, _); graph = build_graph(edges, nodes)
    features = enrich_features(graph, basic_features(graph, nodes), cfg)
    features = assign_base_roles(features, cfg)
    features = apply_coordinators(features, graph, cfg)
    features = cluster_nodes(graph, features, cfg)
    features = score_nodes(features, cfg)
    features, clusters = renumber_and_describe(features, edges, cfg)
    layout = make_layout(graph, cfg)
    top = top_nodes(features, cfg)
    elapsed = time.perf_counter() - started
    export_all(features, edges, clusters, top, layout, cfg, elapsed)
    print("Роли:", features.role.value_counts().sort_index().to_dict())
    print("Кластеров:", int((clusters.cluster_id != cfg["clusters"]["isolated_cluster_id"]).sum()))
    print(top.head(10)[["gid", "role", "priority_score", "why"]].to_string(index=False))
    print(f"Время: {elapsed:.2f} с")


if __name__ == "__main__":
    main()
