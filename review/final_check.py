"""Финальная проверка контракта pipeline. Только чтение, ничего не исправляет."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
ALLOWED_ROLES = {"consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral", "frontier"}


def line(item: str, value, ok: bool) -> None:
    print(f"{item} | {value} | {'OK' if ok else 'FAIL'}")


def main() -> None:
    required_files = ["nodes_roles.csv", "clusters.csv", "top_nodes.csv", "features.parquet",
                       "graph.json", "summary.json", "resilience.json", "cycles.json"]
    missing = [f for f in required_files if not (OUT / f).exists()]
    line("out/ files present", f"missing={missing}", not missing)

    df = pd.read_csv(OUT / "nodes_roles.csv") if (OUT / "nodes_roles.csv").exists() else pd.DataFrame()

    roles_present = set(df["role"].unique()) if "role" in df else set()
    line("roles subset of allowed set", sorted(roles_present), roles_present.issubset(ALLOWED_ROLES))
    line("no isolated role", "isolated" not in roles_present, "isolated" not in roles_present)

    line("row count", len(df), len(df) == 2248)
    required_cols = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
    nulls = {c: int(df[c].isna().sum()) for c in required_cols if c in df}
    no_nulls = all(v == 0 for v in nulls.values()) and len(nulls) == len(required_cols)
    line("no nulls in required cols", nulls, no_nulls)

    if {"depth", "out_deg", "role"}.issubset(df.columns):
        frontier_pool = df[(df["depth"] == 4) & (df["out_deg"] == 0)]
        n_pool = len(frontier_pool)
        n_terminal = int((frontier_pool["role"] == "terminal").sum())
        n_frontier = int((frontier_pool["role"] == "frontier").sum())
    else:
        n_pool, n_terminal, n_frontier = 0, 0, 0
    line("depth=4 & out_deg=0 count", n_pool, n_pool == 444)
    line("terminal + frontier count", n_terminal + n_frontier, n_terminal + n_frontier == 444)
    line("terminal count", n_terminal, 200 <= n_terminal <= 350)

    n_coordinator = int((df["role"] == "coordinator").sum()) if "role" in df else -1
    n_consolidator = int((df["role"] == "consolidator").sum()) if "role" in df else -1
    line("coordinator in [15,30]", n_coordinator, 15 <= n_coordinator <= 30)
    line("consolidator > 24", n_consolidator, n_consolidator > 24)

    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8")) if (OUT / "summary.json").exists() else {}
    auc = summary.get("frontier", {}).get("auc")
    line("frontier.auc in [0.6,0.75]", auc, auc is not None and 0.6 <= auc <= 0.75)

    resilience = json.loads((OUT / "resilience.json").read_text(encoding="utf-8")) if (OUT / "resilience.json").exists() else {}
    n_removed = resilience.get("n_removed", [])
    strategies = ("by_priority", "by_degree", "by_priority_nonseed", "by_degree_nonseed", "random")
    ok = bool(n_removed) and all(len(resilience.get(name, {}).get("lwcc_size", [])) == len(n_removed) and len(resilience.get(name, {}).get("seed_reachable", [])) == len(n_removed) for name in strategies)
    line("resilience format", f"strategies={list(strategies)}", ok)

    elapsed = summary.get("elapsed_seconds")
    line("elapsed_seconds < 60", elapsed, elapsed is not None and elapsed < 60)

    methodology = ROOT / "docs" / "METHODOLOGY.md"
    if methodology.exists():
        n_headings = sum(1 for l in methodology.read_text(encoding="utf-8").splitlines() if l.startswith("## "))
    else:
        n_headings = -1
    line("docs/METHODOLOGY.md headings >= 12", n_headings, n_headings >= 12)

    demo_nodes = ROOT / "docs" / "DEMO_NODES.md"
    line("docs/DEMO_NODES.md exists", demo_nodes.exists(), demo_nodes.exists())

    agent_cfg = ROOT / "agent-docs" / "config.yaml"
    if agent_cfg.exists():
        first_line = agent_cfg.read_text(encoding="utf-8").splitlines()[0] if agent_cfg.read_text(encoding="utf-8").splitlines() else ""
    else:
        first_line = ""
    line("agent-docs/config.yaml first line has 'Справочная копия'", first_line, "Справочная копия" in first_line)

    gitignore = ROOT / ".gitignore"
    gitignore_text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    review_ignored = any(l.strip().rstrip("/") == "review" for l in gitignore_text.splitlines())
    line("review/ in .gitignore", review_ignored, review_ignored)

    log_path = Path("/tmp/pipeline_run.log")
    if log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="ignore")
        n_hits = text.count("RuntimeWarning") + text.count("Traceback")
    else:
        n_hits = -1
    line("pipeline output has no RuntimeWarning/Traceback", f"hits={n_hits}", n_hits == 0)


if __name__ == "__main__":
    main()
