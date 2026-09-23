"""ЭТАП 3: независимый пересчёт признаков и ролей по ТЗ (без импорта pipeline)."""
import json
import math

import networkx as nx
import numpy as np
import pandas as pd
import yaml

DATA = "data"
OUT = "review/out1"

cfg = yaml.safe_load(open("pipeline/config.yaml", encoding="utf-8"))

edges = pd.read_parquet(f"{DATA}/edges.parquet")
nodes = pd.read_parquet(f"{DATA}/nodes.parquet")
for df, cols in ((edges, ("src", "dst")), (nodes, ("gid",))):
    for c in cols:
        df[c] = df[c].astype("int64")

seed_ids = set(nodes.loc[nodes.is_seed, "gid"])

G = nx.DiGraph()
G.add_nodes_from(nodes.gid.tolist())
for r in edges.itertuples(index=False):
    G.add_edge(int(r.src), int(r.dst), sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx), depth=int(r.depth))

feat = nodes[["gid", "depth", "is_seed"]].copy()
in_deg = dict(G.in_degree()); out_deg = dict(G.out_degree())
in_kzt = dict(G.in_degree(weight="sum_kzt")); out_kzt = dict(G.out_degree(weight="sum_kzt"))
feat["in_deg"] = feat.gid.map(in_deg).fillna(0).astype(int)
feat["out_deg"] = feat.gid.map(out_deg).fillna(0).astype(int)
feat["in_kzt"] = feat.gid.map(in_kzt).fillna(0.0)
feat["out_kzt"] = feat.gid.map(out_kzt).fillna(0.0)

ratio = feat.out_kzt / feat.in_kzt.replace(0, np.nan)
feat["pass_ratio"] = ratio.mask(feat.is_seed.astype(bool))

feat["pays_seeds"] = feat.gid.map(lambda g: sum(1 for v in G.successors(int(g)) if v in seed_ids)).astype(int)

cutoff = cfg["features"]["seed_upstream_cutoff"]
upstream = {int(g): 0 for g in feat.gid}
for s in sorted(seed_ids):
    reach = nx.single_source_shortest_path_length(G, s, cutoff=cutoff)
    for g, length in reach.items():
        if length > 0:
            upstream[int(g)] += 1
feat["n_seed_upstream"] = feat.gid.map(upstream).astype(int)

Gw = G.copy()
for _, _, a in Gw.edges(data=True):
    a["distance"] = 1.0 / math.log1p(float(a["sum_kzt"]))
bet = nx.betweenness_centrality(Gw, weight="distance")
feat["betweenness"] = feat.gid.map(bet).fillna(0.0)

feat = feat.set_index("gid", drop=False)


def fmt_kzt(v):
    return f"{v/1_000_000:.2f} млн" if abs(v) >= 1_000_000 else f"{v/1_000:.0f} тыс."


def assign_role(row, cfgr):
    minimum = cfg["data"]["min_tx_kzt"]
    if row.in_deg + row.out_deg == 0:
        return "peripheral", "a: no edges"
    if row.depth == cfg["data"]["max_depth"] and row.out_deg == 0:
        return "frontier", "b: depth==max_depth & out_deg==0"
    d = cfgr["distributor"]
    if row.out_deg >= d["min_out_deg"] and (bool(row.is_seed) or row.out_kzt >= d["min_out_in_ratio"] * row.in_kzt):
        return "distributor", "c"
    c = cfgr["consolidator"]
    if (row.in_deg >= c["min_in_deg"] and row.out_kzt <= c["max_out_in_ratio"] * row.in_kzt) or \
       (row.n_seed_upstream >= c["min_seed_upstream"] and row.in_deg >= c["alt_min_in_deg"]):
        return "consolidator", "d"
    t = cfgr["transit"]
    if (not bool(row.is_seed) and t["min_in_deg"] <= row.in_deg <= t["max_in_deg"] and
            t["min_out_deg"] <= row.out_deg <= t["max_out_deg"] and
            pd.notna(row.pass_ratio) and t["min_pass"] <= row.pass_ratio <= t["max_pass"]):
        return "transit", "e"
    if row.out_deg == 0 and row.depth < cfg["data"]["max_depth"] and row.in_deg >= cfgr["terminal"]["min_in_deg"]:
        return "terminal", "f"
    return "peripheral", "g: fallback"


pass1_roles, rules_hit = {}, {}
for g, row in feat.iterrows():
    role, rule = assign_role(row, cfg["roles"])
    pass1_roles[g] = role
    rules_hit[g] = rule
feat["pass1_role"] = feat.gid.map(pass1_roles)
feat["rule"] = feat.gid.map(rules_hit)

# coordinator pass 2
cc = cfg["roles"]["coordinator"]
hub_set = set(g for g, r in pass1_roles.items() if r in ("consolidator", "distributor"))
hub_payers = {}
for g in feat.gid:
    hub_payers[g] = sum(1 for p in G.predecessors(int(g)) if p in hub_set)
feat["hub_payers"] = feat.gid.map(hub_payers)

final_roles = dict(pass1_roles)
for g, row in feat.iterrows():
    signals = []
    if row.pays_seeds >= cc["min_pays_seeds"] and row.in_deg >= cc["s1_min_in_deg"]:
        signals.append("S1")
    if row.in_deg >= cc["s2_min_in_deg"] and row.out_deg >= cc["s2_min_out_deg"]:
        signals.append("S2")
    if hub_payers[g] >= cc["s3_min_hub_payers"]:
        signals.append("S3")
    if signals:
        final_roles[g] = "coordinator"
feat["expected_role"] = feat.gid.map(final_roles)

print("=== Expected role counts (independent recompute) ===")
print(feat.expected_role.value_counts().to_dict())
print("pass1 (before coordinator overlay):", feat.pass1_role.value_counts().to_dict())
if feat.expected_role.value_counts().get("coordinator", 0) > cc["max_expected"]:
    print(f"WARNING: coordinator count {feat.expected_role.value_counts().get('coordinator')} > max_expected {cc['max_expected']} (config threshold ignored by pipeline)")

# --- compare with Codex's nodes_roles.csv ---
actual = pd.read_csv(f"{OUT}/nodes_roles.csv")[["gid", "role"]].set_index("gid")
cmp = feat[["expected_role"]].join(actual, how="inner").rename(columns={"role": "actual_role"})
print()
print("=== Confusion matrix (expected x actual) ===")
matrix = pd.crosstab(cmp.expected_role, cmp.actual_role)
print(matrix)

mismatches = cmp[cmp.expected_role != cmp.actual_role]
print()
print(f"=== Mismatches: {len(mismatches)} / {len(cmp)} ===")
detail_cols = ["depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "pass_ratio",
               "n_seed_upstream", "pays_seeds", "hub_payers", "rule"]
if len(mismatches):
    sample = feat.loc[mismatches.index[:20], ["expected_role"] + detail_cols].join(mismatches.actual_role)
    print(sample.to_string())

# --- traps from AGENTS.md ---
print()
print("=== Ловушки ===")
d4 = feat[(feat.depth == 4) & (feat.out_deg == 0)]
print("depth==4 & out_deg==0 count (expect 444):", len(d4))
bad_terminal_d4 = actual.loc[actual.index.isin(d4.gid)]
print("of those, how many Codex marked terminal (expect 0):", (bad_terminal_d4.role == "terminal").sum())
print("of those, how many Codex marked frontier (expect 444):", (bad_terminal_d4.role == "frontier").sum())

term_actual = actual.join(feat[["depth"]])
bad_depth_terminal = term_actual[(term_actual.role == "terminal") & (term_actual.depth >= 4)]
print("terminal nodes with depth>=4 in Codex output (expect 0):", len(bad_depth_terminal))

seed_pass_nan = feat[feat.is_seed].pass_ratio.isna().all()
print("all seed pass_ratio is NaN:", seed_pass_nan)
seed_roles = actual.join(feat[["is_seed"]])
print("seed role distribution (Codex):", seed_roles[seed_roles.is_seed].role.value_counts().to_dict())

n3 = (feat.n_seed_upstream >= 3).sum()
print(f"nodes with n_seed_upstream>=3 (orientir ~32 at cutoff=2): {n3}")

print()
print("=== Random 10 gids (random_state=42) + top-10 ===")
rng_sample = feat.sample(10, random_state=42)
top10 = pd.read_csv(f"{OUT}/top_nodes.csv").head(10)
for label, gids in (("RANDOM", rng_sample.gid.tolist()), ("TOP-10", top10.gid.tolist())):
    print(f"--- {label} ---")
    for g in gids:
        r = feat.loc[g]
        a = actual.loc[g, "role"] if g in actual.index else "?"
        ev_row = pd.read_csv(f"{OUT}/nodes_roles.csv").set_index("gid").loc[g] if g in actual.index else None
        ev = ev_row.evidence if ev_row is not None else ""
        print(f"gid={g} depth={r.depth} is_seed={r.is_seed} in_deg={r.in_deg} out_deg={r.out_deg} "
              f"in_kzt={r.in_kzt:.0f} out_kzt={r.out_kzt:.0f} pass_ratio={r.pass_ratio} "
              f"n_seed_upstream={r.n_seed_upstream} hub_payers={r.hub_payers} "
              f"| expected={r.expected_role} ({r.rule}) actual={a}")
        print(f"   evidence: {ev}")
