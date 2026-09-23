"""Базовые приёмочные проверки MUST-HAVE пайплайна."""
from __future__ import annotations

import json
from pathlib import Path
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
    expected = {"nodes_roles.csv", "clusters.csv", "top_nodes.csv", "features.parquet", "graph.json", "summary.json", "resilience.json"}
    assert {path.name for path in output_dir.iterdir()} == expected
    nodes = pd.read_csv(output_dir / "nodes_roles.csv")
    required = {"gid", "role", "role_score", "cluster_id", "priority_score", "evidence", "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "pass_ratio", "n_seed_upstream", "betweenness", "flags", "score_breakdown"}
    assert required.issubset(nodes.columns)
    assert len(nodes) == 2248
    assert nodes["gid"].nunique() == len(nodes)
    assert nodes[["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]].notna().all().all()
    assert set(nodes["role"]).issubset(ALLOWED_ROLES)
    graph = json.loads((output_dir / "graph.json").read_text(encoding="utf-8"))
    assert len(graph["nodes"]) == 2248 and len(graph["edges"]) == 3119
    assert all(isinstance(node["id"], str) for node in graph["nodes"])
    assert all(isinstance(edge["source"], str) and isinstance(edge["target"], str) for edge in graph["edges"])


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
    assert nodes.loc[frontier, "role"].eq("frontier").all()
    assert len(nodes.loc[frontier]) == 444


def test_output_csv_is_deterministic(tmp_path: Path) -> None:
    """Два прогона с seed из config дают идентичные пользовательские CSV."""
    first, second = tmp_path / "first", tmp_path / "second"
    command = [sys.executable, "-m", "pipeline", "--data", "data"]
    for target in (first, second):
        subprocess.run(command + ["--out", str(target)], cwd=ROOT, check=True, timeout=60, capture_output=True, text=True)
    for name in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
