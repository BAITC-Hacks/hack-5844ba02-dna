"""Role-threshold sensitivity measured by top-priority overlap."""
from __future__ import annotations

from copy import deepcopy

import networkx as nx
import pandas as pd

from .roles import apply_coordinators, assign_base_roles
from .scoring import score_nodes


def _scale_role_thresholds(config: dict, factor: float) -> dict:
    """Scale rule cutoffs while leaving scoring calibration and bonuses unchanged."""
    cfg = deepcopy(config)
    for section in ("coordinator", "distributor", "consolidator", "transit", "terminal", "temporal"):
        for name, value in cfg["roles"][section].items():
            if isinstance(value, (int, float)) and (name.startswith("min_") or name.startswith("max_")):
                cfg["roles"][section][name] = value * factor
    cfg["roles"]["frontier"]["terminal_threshold"] *= factor
    return cfg


def top20_sensitivity(features: pd.DataFrame, graph: nx.DiGraph, cfg: dict) -> dict:
    """Compare top-N overlap after one recalculation at each cutoff multiplier."""
    size = int(cfg["sensitivity"]["top_n"])
    baseline = set(features.nlargest(size, "priority_score").gid.astype(int))
    outcomes = {}
    for factor in cfg["sensitivity"]["role_threshold_factors"]:
        alternative_cfg = _scale_role_thresholds(cfg, float(factor))
        alternative = assign_base_roles(features, alternative_cfg)
        alternative = apply_coordinators(alternative, graph, alternative_cfg)
        alternative = score_nodes(alternative, alternative_cfg)
        candidate = set(alternative.nlargest(size, "priority_score").gid.astype(int))
        outcomes[str(factor)] = len(baseline & candidate) / size
    return outcomes
