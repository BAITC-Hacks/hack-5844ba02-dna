"""Proportional attribution of observed value to seed funds."""
from __future__ import annotations

import numpy as np
import networkx as nx
import pandas as pd


def add_seed_flow(graph: nx.DiGraph, features: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Iteratively attribute seed money under proportional mixing.

    Seed nodes start with share one.  A non-seed node's share is incoming seed value
    divided by the larger observed in/out turnover, clipping external funding to zero
    through one.  Repeated relaxation handles cycles without assuming an acyclic graph.
    """
    result = features.copy()
    gids = result.gid.astype(int).tolist()
    seed_ids = set(result.loc[result.is_seed.astype(bool), "gid"].astype(int))
    denominator = result.set_index("gid")[["in_kzt", "out_kzt"]].max(axis=1).to_dict()
    share = {gid: 1.0 if gid in seed_ids else 0.0 for gid in gids}
    settings = cfg["flow"]
    seed_in: dict[int, float] = {gid: 0.0 for gid in gids}
    for _ in range(int(settings["max_iter"])):
        seed_in = {gid: 0.0 for gid in gids}
        for source, target, attrs in graph.edges(data=True):
            seed_in[int(target)] += float(attrs["sum_kzt"]) * share[int(source)]
        updated = {
            gid: 1.0 if gid in seed_ids else float(np.clip(seed_in[gid] / max(float(denominator[gid]), 1.0), 0.0, 1.0))
            for gid in gids
        }
        delta = max(abs(updated[gid] - share[gid]) for gid in gids)
        share = updated
        if delta <= float(settings["tol"]):
            break
    seed_in = {gid: 0.0 for gid in gids}
    for source, target, attrs in graph.edges(data=True):
        seed_in[int(target)] += float(attrs["sum_kzt"]) * share[int(source)]
    result["seed_flow_kzt"] = result.gid.map(seed_in).astype(float)
    result["seed_share"] = result.gid.map(share).astype(float)
    return result
