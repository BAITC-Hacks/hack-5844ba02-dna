"""ЭТАП 2: проверка контракта выходных файлов. Не импортирует pipeline."""
import json
import re
import pandas as pd

OUT = "review/out1"
ALLOWED_ROLES = {"consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral", "frontier"}
BANNED_WORDS = ["виновен", "преступник"]

nodes = pd.read_parquet("data/nodes.parquet")
nr = pd.read_csv(f"{OUT}/nodes_roles.csv")

print("=== nodes_roles.csv ===")
print("rows:", len(nr), "(expect 2248)")
print("unique gid:", nr.gid.nunique(), "== rows?", nr.gid.nunique() == len(nr))
print("gid set == nodes.parquet gid set?", set(nr.gid) == set(nodes.gid))
seed_gids = set(nodes[nodes.is_seed]["gid"])
edges = pd.read_parquet("data/edges.parquet")
incident = set(edges.src) | set(edges.dst)
isolated_seed = seed_gids - incident
print("isolated seed count (expect 19):", len(isolated_seed))
print("isolated seed present in nodes_roles:", isolated_seed.issubset(set(nr.gid)))

required_cols = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
for c in required_cols:
    n_missing = nr[c].isna().sum()
    print(f"col {c}: present={c in nr.columns}, NaN count={n_missing}")

extra_required = ["depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx", "out_tx",
                  "pass_ratio", "seed_flow_kzt", "seed_share", "n_seed_upstream", "p_terminal",
                  "betweenness", "fast_pass_share", "max_sync_payers", "near_threshold_share",
                  "n_cycles", "flags", "score_breakdown"]
present = [c for c in extra_required if c in nr.columns]
missing = [c for c in extra_required if c not in nr.columns]
print("extra/optional TASK columns present:", present)
print("extra/optional TASK columns MISSING:", missing)

bad_roles = set(nr.role.unique()) - ALLOWED_ROLES
print("roles used:", nr.role.value_counts().to_dict())
print("roles outside allowed dict:", bad_roles)

print("role_score range:", nr.role_score.min(), nr.role_score.max(), "in [0,1]?", nr.role_score.between(0, 1).all())
print("priority_score range:", nr.priority_score.min(), nr.priority_score.max(), "in [0,1]?", nr.priority_score.between(0, 1).all())

ev = nr.evidence.astype(str)
print("evidence empty count:", (ev.str.len() == 0).sum())
print("evidence > 200 chars count:", (ev.str.len() > 200).sum())
print("evidence without any digit count:", (~ev.str.contains(r"\d")).sum())
for w in BANNED_WORDS:
    print(f"evidence containing banned word '{w}':", ev.str.contains(w, case=False).sum())
# "организатор" as assertion (not "кандидат в координирующий узел")
org_hits = nr[ev.str.contains("организатор", case=False)]
print("evidence containing 'организатор' (any form):", len(org_hits))

print()
print("=== clusters.csv ===")
cl = pd.read_csv(f"{OUT}/clusters.csv")
print("columns:", list(cl.columns))
print("sum n_nodes (expect 2248):", cl.n_nodes.sum())
print("sum n_seed (expect 81):", cl.n_seed.sum())
print("cluster 0 role composition (should be all/mostly isolated):",
      nr[nr.cluster_id == 0].shape[0], "nodes; is it exactly the isolated set?",
      set(nr[nr.cluster_id == 0].gid) == (set(nr.gid) - incident))

print()
print("=== top_nodes.csv ===")
tn = pd.read_csv(f"{OUT}/top_nodes.csv")
print("rows (expect 50):", len(tn))
print("rank sequence 1..50?", list(tn["rank"]) == list(range(1, len(tn) + 1)))
print("priority_score non-increasing?", tn.priority_score.is_monotonic_decreasing)
print("why <=20 chars count:", (tn.why.astype(str).str.len() <= 20).sum())

print()
print("=== graph.json ===")
g = json.loads(open(f"{OUT}/graph.json", encoding="utf-8").read())
print("n nodes (expect 2248):", len(g["nodes"]))
print("n edges (expect 3119):", len(g["edges"]))
bad_id_types = sum(1 for n in g["nodes"] if not isinstance(n["id"], str))
bad_src_types = sum(1 for e in g["edges"] if not isinstance(e["source"], str) or not isinstance(e["target"], str))
print("node ids not string:", bad_id_types)
print("edge source/target not string:", bad_src_types)
missing_xy = sum(1 for n in g["nodes"] if n.get("x") is None or n.get("y") is None)
nan_xy = sum(1 for n in g["nodes"] if isinstance(n.get("x"), float) and n["x"] != n["x"])
print("nodes missing x/y:", missing_xy, "NaN x:", nan_xy)
