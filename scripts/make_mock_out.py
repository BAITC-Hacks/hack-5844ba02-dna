#!/usr/bin/env python3
"""Create deterministic viewer fixtures matching the pipeline output contract."""

import csv
import json
import math
import random
from pathlib import Path

ROLES = ["consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral", "frontier"]


def gid_for(index: int) -> str:
    return f"1000000{index:011d}"


def make_nodes(count: int = 300) -> list[dict]:
    rng = random.Random(5844)
    nodes = []
    for i in range(count):
        role = ROLES[i % len(ROLES)]
        cluster = i % 5
        priority = round(0.35 + ((i * 37) % 65) / 100, 4)
        role_score = round(0.55 + ((i * 19) % 45) / 100, 4)
        angle = 2 * math.pi * i / count
        radius = 260 + cluster * 38 + rng.uniform(-18, 18)
        nodes.append({
            "id": gid_for(i), "role": role, "cluster": cluster,
            "priority": priority, "role_score": role_score,
            "depth": i % 5, "is_seed": i < 15,
            "x": round(math.cos(angle) * radius, 3),
            "y": round(math.sin(angle) * radius, 3),
            "in_kzt": round(30_000 + ((i * 7919) % 1_900_000), 2),
            "out_kzt": round(20_000 + ((i * 4567) % 1_600_000), 2),
            "in_deg": (i * 3) % 12, "out_deg": (i * 5) % 14,
            "pass_ratio": round(0.2 + ((i * 13) % 180) / 100, 4),
            "n_seed_upstream": i % 4, "betweenness": round((i % 100) / 100, 4),
            "flags": "seed" if i < 15 else ("frontier" if role == "frontier" else ""),
            "evidence": f"Mock evidence: {((i * 3) % 18) + 1} links; {int(20_000 + ((i * 4567) % 1_600_000)):,} KZT.",
            "score_breakdown": {"flow": round(priority * 0.45, 4), "structure": round(role_score * 0.35, 4), "risk": 0.2},
        })
    return nodes


def make_edges(nodes: list[dict]) -> list[dict]:
    edges = []
    for i, node in enumerate(nodes):
        for step in (1, 5, 17):
            j = (i + step) % len(nodes)
            edges.append({"source": node["id"], "target": nodes[j]["id"], "sum_kzt": 5_000 + ((i * 997 + step * 131) % 950_000), "n_tx": 1 + (i + step) % 8})
    return edges


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in columns} for row in rows)


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "out"
    out.mkdir(parents=True, exist_ok=True)
    nodes = make_nodes()
    edges = make_edges(nodes)
    node_columns = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence", "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "pass_ratio", "n_seed_upstream", "betweenness", "flags", "score_breakdown"]
    node_rows = []
    for node in nodes:
        row = dict(node)
        row.update({"gid": node["id"], "cluster_id": node["cluster"], "priority_score": node["priority"], "score_breakdown": json.dumps(node["score_breakdown"], separators=(",", ":"))})
        node_rows.append(row)
    write_csv(out / "nodes_roles.csv", node_rows, node_columns)
    clusters = []
    for cluster in range(5):
        members = [n for n in nodes if n["cluster"] == cluster]
        internal = sum(e["sum_kzt"] for e in edges if next(n for n in nodes if n["id"] == e["source"])["cluster"] == cluster and next(n for n in nodes if n["id"] == e["target"])["cluster"] == cluster)
        clusters.append({"cluster_id": cluster, "n_nodes": len(members), "n_seed": sum(n["is_seed"] for n in members), "sum_kzt_internal": round(internal, 2), "top_gids": ",".join(n["id"] for n in sorted(members, key=lambda n: n["priority"], reverse=True)[:5]), "hypothesis": f"Cluster {cluster}: mixed flow hypothesis requiring review."})
    write_csv(out / "clusters.csv", clusters, ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"])
    top = sorted(nodes, key=lambda n: n["priority"], reverse=True)[:50]
    write_csv(out / "top_nodes.csv", [{"rank": i + 1, "gid": n["id"], "role": n["role"], "priority_score": n["priority"], "why": n["evidence"]} for i, n in enumerate(top)], ["rank", "gid", "role", "priority_score", "why"])
    graph_nodes = [{key: node[key] for key in ("id", "role", "cluster", "priority", "role_score", "depth", "is_seed", "x", "y", "in_kzt", "out_kzt")} for node in nodes]
    (out / "graph.json").write_text(json.dumps({"nodes": graph_nodes, "edges": edges}, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote mock viewer data to {out} ({len(nodes)} nodes, {len(edges)} edges)")


if __name__ == "__main__":
    main()
