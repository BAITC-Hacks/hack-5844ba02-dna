"""Базовые приёмочные проверки MUST-HAVE пайплайна."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROLES = {"consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral", "frontier"}


@pytest.fixture(scope="module")
def output_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Один раз запускает пайплайн на настоящем датасете без сети."""
    out = tmp_path_factory.mktemp("pipeline-output")
    subprocess.run(
        [sys.executable, "-m", "pipeline", "--data", "data", "--out", str(out)],
        cwd=ROOT,
        check=True,
        timeout=60,
        capture_output=True,
        text=True,
    )
    return out


def test_contract_and_json_identifiers(output_dir: Path) -> None:
    """Проверяет обязательные файлы, строки всех узлов и JSON gid как строки."""
    expected = {"nodes_roles.csv", "clusters.csv", "top_nodes.csv", "features.parquet", "graph.json", "summary.json", "resilience.json", "cycles.json"}
    assert {path.name for path in output_dir.iterdir()} == expected
    nodes = pd.read_csv(output_dir / "nodes_roles.csv")
    required = {"gid", "role", "role_score", "cluster_id", "priority_score", "evidence", "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx", "out_tx", "pass_ratio", "n_seed_upstream", "betweenness", "flags", "score_breakdown"}
    assert required.issubset(nodes.columns)
    assert len(nodes) == 2248
    assert nodes["gid"].nunique() == len(nodes)
    source_gids = set(pd.read_parquet(ROOT / "data" / "nodes.parquet").gid.astype("int64"))
    assert set(nodes.gid.astype("int64")) == source_gids
    assert nodes[["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]].notna().all().all()
    assert set(nodes["role"]).issubset(ALLOWED_ROLES)
    assert nodes["role_score"].between(0, 1).all()
    assert nodes["priority_score"].between(0, 1).all()
    assert nodes["evidence"].str.len().le(200).all()
    assert nodes["evidence"].map(lambda text: bool(re.search(r"\d", text))).all()
    assert not nodes["evidence"].str.lower().str.contains("виновен|преступник").any()
    graph = json.loads((output_dir / "graph.json").read_text(encoding="utf-8"))
    assert len(graph["nodes"]) == 2248 and len(graph["edges"]) == 3119
    assert all(isinstance(node["id"], str) for node in graph["nodes"])
    assert all(isinstance(edge["source"], str) and isinstance(edge["target"], str) for edge in graph["edges"])
    assert {"id", "role", "cluster", "priority", "role_score", "depth", "is_seed", "x", "y", "in_kzt", "out_kzt"}.issubset(graph["nodes"][0])
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert {"auc", "coefficients", "n_terminal_est", "n_frontier"}.issubset(summary["frontier"])
    assert 0 <= summary["frontier"]["auc"] <= 1
    assert summary["role_counts"] == nodes["role"].value_counts().sort_index().to_dict()
    assert summary["elapsed_seconds"] > 0
    assert {"load", "enrich_features", "export"}.issubset(summary["stage_seconds"])
    assert summary["elapsed_seconds"] < 300


def test_features_and_frontier_rule(output_dir: Path) -> None:
    """Проверяет pass_ratio и приоритет frontier над terminal на последнем колене."""
    cfg = yaml.safe_load((ROOT / "pipeline" / "config.yaml").read_text(encoding="utf-8"))
    nodes = pd.read_csv(output_dir / "nodes_roles.csv")
    seeds = nodes["is_seed"].astype(bool)
    assert nodes.loc[seeds, "pass_ratio"].isna().all()
    observed = nodes.loc[~seeds & nodes["in_kzt"].gt(0), "pass_ratio"]
    expected = (nodes.loc[~seeds & nodes["in_kzt"].gt(0), "out_kzt"] / nodes.loc[~seeds & nodes["in_kzt"].gt(0), "in_kzt"])
    assert np.allclose(observed, expected, equal_nan=True)
    frontier = nodes["depth"].eq(cfg["data"]["max_depth"]) & nodes["out_deg"].eq(0)
    assert len(nodes.loc[frontier]) == 444
    assert nodes.loc[frontier, "role"].isin({"terminal", "frontier"}).all()
    assert nodes.loc[frontier, "p_terminal"].between(0, 1).all()
    assert nodes.loc[frontier, "evidence"].str.contains("аналог", case=False).all()
    assert nodes.loc[frontier, "p_terminal"].notna().all()
    assert nodes["seed_flow_kzt"].ge(0).all()


def test_clusters_top_graph_and_resilience_contract(output_dir: Path) -> None:
    nodes = pd.read_csv(output_dir / "nodes_roles.csv")
    clusters = pd.read_csv(output_dir / "clusters.csv")
    top = pd.read_csv(output_dir / "top_nodes.csv")
    graph = json.loads((output_dir / "graph.json").read_text(encoding="utf-8"))
    resilience = json.loads((output_dir / "resilience.json").read_text(encoding="utf-8"))
    assert clusters.n_nodes.sum() == 2248 and clusters.n_seed.sum() == 81
    assert set(nodes.cluster_id).issubset(set(clusters.cluster_id))
    assert len(top) >= 20 and top["rank"].tolist() == list(range(1, len(top) + 1))
    assert top.priority_score.is_monotonic_decreasing and top.why.str.len().gt(20).all()
    assert len(graph["nodes"]) == 2248 and len(graph["edges"]) == 3119
    assert all(isinstance(item["id"], str) and item["x"] is not None and item["y"] is not None for item in graph["nodes"])
    levels = resilience["n_removed"]
    for strategy in ("by_priority", "by_degree", "by_priority_nonseed", "by_degree_nonseed", "random"):
        assert len(resilience[strategy]["lwcc_size"]) == len(levels)
        assert len(resilience[strategy]["seed_reachable"]) == len(levels)


def test_summary_cycles_and_coordinators(output_dir: Path) -> None:
    nodes = pd.read_csv(output_dir / "nodes_roles.csv")
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    cycles = json.loads((output_dir / "cycles.json").read_text(encoding="utf-8"))
    assert summary["frontier"]["auc"] > 0.5
    assert 5 <= int(nodes.role.eq("coordinator").sum()) <= 30
    assert all(isinstance(gid, str) for cycle in cycles for gid in cycle)


def test_output_csv_is_deterministic(tmp_path: Path) -> None:
    """Два прогона с seed из config дают идентичные пользовательские CSV."""
    first, second = tmp_path / "first", tmp_path / "second"
    command = [sys.executable, "-m", "pipeline", "--data", "data"]
    for target in (first, second):
        subprocess.run(command + ["--out", str(target)], cwd=ROOT, check=True, timeout=60, capture_output=True, text=True)
    for name in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
