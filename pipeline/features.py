"""Базовые структурные и потоковые признаки направленного графа."""
import math
import logging

import networkx as nx
import numpy as np
import pandas as pd

LOG = logging.getLogger(__name__)


def _pagerank_without_scipy(graph: nx.DiGraph, alpha: float = 0.85, steps: int = 100) -> dict[int, float]:
    """Deterministic weighted PageRank fallback when NetworkX SciPy is unavailable."""
    nodes = list(graph.nodes())
    if not nodes:
        return {}
    score = {node: 1.0 / len(nodes) for node in nodes}
    for _ in range(steps):
        next_score = {node: (1.0 - alpha) / len(nodes) for node in nodes}
        dangling = sum(score[node] for node in nodes if graph.out_degree(node) == 0)
        share = alpha * (dangling / len(nodes))
        for node in nodes:
            next_score[node] += share
        for source in nodes:
            outgoing = list(graph.out_edges(source, data="sum_kzt"))
            total = sum(float(weight or 0.0) for _, _, weight in outgoing)
            if not outgoing or total <= 0:
                continue
            for _, target, weight in outgoing:
                next_score[target] += alpha * score[source] * float(weight) / total
        score = next_score
    return score


def basic_features(graph: nx.DiGraph, nodes: pd.DataFrame) -> pd.DataFrame:
    """Считает степени, обороты и PageRank из стартового решения."""
    result = nodes[["gid", "depth", "is_seed"]].copy()
    result["in_deg"] = result.gid.map(dict(graph.in_degree())).fillna(0).astype(int)
    result["out_deg"] = result.gid.map(dict(graph.out_degree())).fillna(0).astype(int)
    result["in_kzt"] = result.gid.map(dict(graph.in_degree(weight="sum_kzt"))).fillna(0.0)
    result["out_kzt"] = result.gid.map(dict(graph.out_degree(weight="sum_kzt"))).fillna(0.0)
    result["in_tx"] = result.gid.map(dict(graph.in_degree(weight="n_tx"))).fillna(0).astype(int)
    result["out_tx"] = result.gid.map(dict(graph.out_degree(weight="n_tx"))).fillna(0).astype(int)
    try:
        pagerank = nx.pagerank(graph, weight="sum_kzt")
    except ModuleNotFoundError:
        pagerank = _pagerank_without_scipy(graph)
    result["pagerank"] = result.gid.map(pagerank).fillna(0.0)
    return result


def _weighted_betweenness(graph: nx.DiGraph) -> dict[int, float]:
    """Большая сумма задаёт короткий путь для поиска посредников."""
    weighted = graph.copy()
    for _, _, attrs in weighted.edges(data=True):
        attrs["distance"] = 1.0 / math.log1p(float(attrs["sum_kzt"]))
    return nx.betweenness_centrality(weighted, weight="distance")


def enrich_features(graph: nx.DiGraph, features: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Добавляет pass_ratio, связи с seed и centrality согласно конфигу."""
    result = features.copy()
    ratio = result["out_kzt"] / result["in_kzt"].replace(0, np.nan)
    result["pass_ratio"] = ratio.mask(result["is_seed"].astype(bool))
    seed_ids = set(result.loc[result["is_seed"], "gid"].astype(int))
    result["pays_seeds"] = result["gid"].map(lambda gid: sum(int(v in seed_ids) for v in graph.successors(int(gid)))).astype(int)
    upstream: dict[int, int] = {int(gid): 0 for gid in result["gid"]}
    cutoff = cfg["features"]["seed_upstream_cutoff"]
    for seed in sorted(seed_ids):
        reachable = nx.single_source_shortest_path_length(graph, seed, cutoff=cutoff)
        for gid, length in reachable.items():
            if gid != seed and length > 0:
                upstream[int(gid)] += 1
    result["n_seed_upstream"] = result["gid"].map(upstream).astype(int)
    LOG.info("Расчёт betweenness")
    result["betweenness"] = result["gid"].map(_weighted_betweenness(graph)).fillna(0.0)
    return result
