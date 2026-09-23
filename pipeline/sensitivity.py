"""Role-threshold sensitivity measured by top-priority overlap."""
from __future__ import annotations

from copy import deepcopy

import networkx as nx
import pandas as pd

from .roles import apply_coordinators, assign_base_roles
from .scoring import score_nodes

_SCALED_ROLE_THRESHOLDS = {
    "coordinator": {"min_pays_seeds", "s1_min_in_deg", "s2_min_in_deg", "s2_min_out_deg", "s3_min_hub_payers", "s3_min_in_deg", "s3_min_out_deg"},
    "distributor": {"min_out_deg", "min_out_in_ratio"},
    "consolidator": {"min_in_deg", "max_out_in_ratio", "min_seed_upstream", "alt_min_in_deg"},
    "transit": {"min_in_deg", "min_out_deg", "max_in_deg", "max_out_deg", "min_pass", "max_pass"},
    "terminal": {"min_in_deg"},
    "temporal": {"fast_pass_min_share", "sync_min_payers", "near_threshold_min_share", "cycles_min_count"},
}


def _scale_role_thresholds(config: dict, factor: float) -> dict:
    """Scale only named decision cutoffs, never warning limits or score bonuses."""
    cfg = deepcopy(config)
    for section, names in _SCALED_ROLE_THRESHOLDS.items():
        for name in names:
            cfg["roles"][section][name] *= factor
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
