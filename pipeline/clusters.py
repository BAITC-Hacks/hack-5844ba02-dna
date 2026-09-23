"""Кластеризация Louvain и интерпретация сообществ."""
import json
import math
import networkx as nx
import pandas as pd


def cluster_nodes(graph: nx.DiGraph, features: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Louvain на проекции: направление теряется только для кластеризации."""
    undirected = nx.Graph()
    active = [node for node in graph if graph.degree(node) > 0]
    undirected.add_nodes_from(active)
    for source, target, attrs in graph.edges(data=True):
        weight = float(attrs["sum_kzt"])
        if undirected.has_edge(source, target): undirected[source][target]["amount"] += weight
        else: undirected.add_edge(source, target, amount=weight)
    for _, _, attrs in undirected.edges(data=True): attrs["weight"] = math.log1p(attrs.pop("amount"))
    communities = nx.community.louvain_communities(undirected, weight="weight", resolution=cfg["clusters"]["resolution"], seed=cfg["seed"])
    membership = {int(gid): idx + 1 for idx, community in enumerate(communities) for gid in community}
    result = features.copy()
    result["cluster_id"] = result.gid.map(membership).fillna(cfg["clusters"]["isolated_cluster_id"]).astype(int)
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
        elif n_seed == 1 and len(group) < cfg["clusters"]["small_fragment_max_nodes"]: hypothesis = "Периферийный фрагмент одного seed"
        else: hypothesis = "Состав ролей: " + ", ".join(f"{role} {count}" for role, count in sorted(roles.items()))
        rows.append({"cluster_id": int(cid), "n_nodes": len(group), "n_seed": n_seed, "sum_kzt_internal": internal, "top_gids": ";".join(str(int(gid)) for gid in top.gid), "hypothesis": hypothesis[:200], "role_counts": json.dumps(roles, ensure_ascii=False, sort_keys=True)})
    return result, pd.DataFrame(rows)
