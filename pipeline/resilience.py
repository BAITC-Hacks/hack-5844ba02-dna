"""Network robustness under deterministic priority, degree and random removals."""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd


def _metrics(graph: nx.DiGraph, seeds: set[int]) -> tuple[int, int]:
    """Return largest weak component and non-seed nodes reachable from retained seeds."""
    lwcc = max((len(part) for part in nx.weakly_connected_components(graph)), default=0)
    reachable: set[int] = set()
    for seed in sorted(seeds.intersection(graph)):
        reachable.update(nx.descendants(graph, seed))
    return lwcc, len(reachable - seeds)


def _after_removal(graph: nx.DiGraph, seeds: set[int], removed: list[int]) -> tuple[int, int]:
    """Copy graph and calculate metrics after a concrete removal set."""
    reduced = graph.copy()
    reduced.remove_nodes_from(removed)
    return _metrics(reduced, seeds - set(removed))


def calculate_resilience(graph: nx.DiGraph, features: pd.DataFrame, cfg: dict) -> dict:
    """Evaluate removal strategies; random metrics are means over seeded trials."""
    settings = cfg["resilience"]
    levels = [int(value) for value in settings["n_removed"]]
    gids = features.gid.astype(int).tolist()
    seeds = set(features.loc[features.is_seed.astype(bool), "gid"].astype(int))
    priority = features.sort_values(["priority_score", "gid"], ascending=[False, True]).gid.astype(int).tolist()
    degree = features.assign(_degree=features.in_deg + features.out_deg).sort_values(["_degree", "gid"], ascending=[False, True]).gid.astype(int).tolist()
    nonseed = features.loc[~features.is_seed.astype(bool)]
    priority_nonseed = nonseed.sort_values(["priority_score", "gid"], ascending=[False, True]).gid.astype(int).tolist()
    degree_nonseed = nonseed.assign(_degree=nonseed.in_deg + nonseed.out_deg).sort_values(["_degree", "gid"], ascending=[False, True]).gid.astype(int).tolist()
    result = {"n_removed": levels}
    for name, ordered in (("by_priority", priority), ("by_degree", degree),
                          ("by_priority_nonseed", priority_nonseed), ("by_degree_nonseed", degree_nonseed)):
        values = [_after_removal(graph, seeds, ordered[:level]) for level in levels]
        result[name] = {"lwcc_size": [item[0] for item in values], "seed_reachable": [item[1] for item in values]}
    random_lwcc, random_reachable = [], []
    for level in levels:
        trials = []
        for index in range(int(settings["random_runs"])):
            ordered = np.random.default_rng(cfg["seed"] + index).permutation(gids).tolist()
            trials.append(_after_removal(graph, seeds, ordered[:level]))
        random_lwcc.append(float(np.mean([item[0] for item in trials])))
        random_reachable.append(float(np.mean([item[1] for item in trials])))
    result["random"] = {"lwcc_size": random_lwcc, "seed_reachable": random_reachable}
    return result
