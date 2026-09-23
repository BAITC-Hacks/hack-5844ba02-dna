"""Кластеризация Louvain и интерпретация сообществ."""
import json
import math
import networkx as nx
import pandas as pd
from sklearn.metrics import adjusted_rand_score


def _undirected_projection(graph: nx.DiGraph) -> nx.Graph:
    """Build the weighted projection; direction is lost only for clustering."""
    undirected = nx.Graph()
    active = [node for node in graph if graph.degree(node) > 0]
    undirected.add_nodes_from(active)
    for source, target, attrs in graph.edges(data=True):
        amount = float(attrs["sum_kzt"])
        if undirected.has_edge(source, target): undirected[source][target]["amount"] += amount
        else: undirected.add_edge(source, target, amount=amount)
    for _, _, attrs in undirected.edges(data=True): attrs["weight"] = math.log1p(attrs.pop("amount"))
    return undirected


def _membership(undirected: nx.Graph, cfg: dict, seed: int) -> dict[int, int]:
    """Produce labels for a single deterministic Louvain run."""
    communities = nx.community.louvain_communities(undirected, weight="weight", resolution=cfg["clusters"]["resolution"], seed=seed)
    return {int(gid): index + 1 for index, community in enumerate(communities) for gid in community}


def cluster_nodes(graph: nx.DiGraph, features: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Louvain на проекции: направление теряется только для кластеризации."""
    undirected = _undirected_projection(graph)
    membership = _membership(undirected, cfg, cfg["seed"])
    ordered = sorted(undirected.nodes())
    reference = [membership[int(gid)] for gid in ordered]
    aris = []
    for seed in range(int(cfg["clusters"]["stability_runs"])):
        alternative = _membership(undirected, cfg, seed)
        aris.append(float(adjusted_rand_score(reference, [alternative[int(gid)] for gid in ordered])))
    result = features.copy()
    result["cluster_id"] = result.gid.map(membership).fillna(cfg["clusters"]["isolated_cluster_id"]).astype(int)
    return result, {"ari_mean": float(sum(aris) / len(aris)) if aris else 1.0}


def add_bridge_flags(features: pd.DataFrame, graph: nx.DiGraph, cfg: dict) -> pd.DataFrame:
    """Flag high-betweenness nodes connecting seed-bearing communities."""
    result = features.copy()
    cutoff = result.betweenness.quantile(cfg["clusters"]["bridge_betweenness_percentile"] / 100)
    seed_clusters = set(result.loc[result.is_seed.astype(bool), "cluster_id"].astype(int))
    cluster_by_gid = result.set_index("gid").cluster_id.to_dict()
    flags = []
    for row in result.itertuples():
        neighbors = set(graph.predecessors(int(row.gid))).union(graph.successors(int(row.gid)))
        linked = {int(cluster_by_gid[gid]) for gid in neighbors if int(cluster_by_gid[gid]) in seed_clusters}
        current = list(row.flags) if isinstance(row.flags, list) else str(row.flags).split(";") if row.flags else []
        if row.betweenness >= cutoff and len(linked) >= 2:
            current.append("bridge")
        flags.append(current)
    result["flags"] = flags
    return result


def renumber_and_describe(features: pd.DataFrame, edges: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Нумерует кластеры по priority и формирует clusters.csv."""
    result = features.copy()
    priorities = result.groupby("cluster_id").priority_score.sum().sort_values(ascending=False)
    zero = cfg["clusters"]["isolated_cluster_id"]
    ids = [int(cid) for cid in priorities.index if cid != zero]
    mapping = {zero: zero, **{old: new for new, old in enumerate(ids, 1)}}
    result["cluster_id"] = result.cluster_id.map(mapping).astype(int)
    rows = []
    for cid, group in result.groupby("cluster_id", sort=True):
        gids = set(group.gid.astype(int)); internal = edges[edges.src.isin(gids) & edges.dst.isin(gids)].sum_kzt.sum()
        roles = group.role.value_counts().to_dict(); n_seed = int(group.is_seed.sum())
        top = group.sort_values(["priority_score", "gid"], ascending=[False, True]).head(cfg["clusters"]["top_gids"])
        if cid == zero: hypothesis = f"Изолированные клиенты без переводов ≥{cfg['data']['min_tx_kzt']} KZT"
        elif roles.get("consolidator", 0) and n_seed >= cfg["clusters"]["min_seeds_for_collection"]:
            hypothesis = f"Сбор выручки: {n_seed} seed → {roles['consolidator']} точек консолидации, оборот {internal / 1_000_000:.2f} млн"
        elif roles.get("distributor", 0) or roles.get("coordinator", 0):
            max_out = int(group.out_deg.max()); hypothesis = f"Распределительный узел: веерная рассылка на {max_out} получателей"
        elif roles.get("transit", 0) / len(group) >= cfg["clusters"]["min_transit_share"]:
            hypothesis = f"Транзитные цепочки: {roles['transit']} узлов пропускают средства дальше"
        elif n_seed == 1 and len(group) < cfg["clusters"]["small_fragment_max_nodes"]: hypothesis = "Периферийный фрагмент одного seed"
        else: hypothesis = "Состав ролей: " + ", ".join(f"{role} {count}" for role, count in sorted(roles.items()))
        rows.append({"cluster_id": int(cid), "n_nodes": len(group), "n_seed": n_seed, "sum_kzt_internal": internal, "top_gids": ";".join(str(int(gid)) for gid in top.gid), "hypothesis": hypothesis[:200], "role_counts": json.dumps(roles, ensure_ascii=False, sort_keys=True)})
    return result, pd.DataFrame(rows)
