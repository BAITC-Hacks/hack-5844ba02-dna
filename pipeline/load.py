"""Загрузка входных файлов и построение направленного графа переводов."""
from pathlib import Path
import logging

import networkx as nx
import numpy as np
import pandas as pd

LOG = logging.getLogger(__name__)


def load(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Загружает три parquet-файла, сохраняя gid как int64."""
    edges = pd.read_parquet(data_dir / "edges.parquet")
    nodes = pd.read_parquet(data_dir / "nodes.parquet")
    transactions = pd.read_parquet(data_dir / "transactions.parquet")
    for frame, cols in ((edges, ("src", "dst")), (nodes, ("gid",)), (transactions, ("src", "dst"))):
        for col in cols:
            frame[col] = frame[col].astype("int64")
    transactions["date"] = pd.to_datetime(transactions["date"])
    return edges, nodes, transactions


def sanity_check(edges: pd.DataFrame, nodes: pd.DataFrame, transactions: pd.DataFrame) -> set[int]:
    """Проверяет согласованность агрегированных и исходных переводов."""
    required_edges = {"src", "dst", "sum_kzt", "n_tx", "depth"}
    required_nodes = {"gid", "depth", "is_seed"}
    required_transactions = {"src", "dst", "sum_kzt", "date"}
    if (not required_edges.issubset(edges) or not required_nodes.issubset(nodes)
            or not required_transactions.issubset(transactions)):
        raise ValueError("Входные parquet-файлы не соответствуют контракту")
    if nodes["gid"].duplicated().any() or edges.duplicated(["src", "dst"]).any():
        raise ValueError("gid и агрегированные пары src/dst должны быть уникальны")
    numeric = pd.concat([edges["sum_kzt"], transactions["sum_kzt"]], ignore_index=True)
    if not np.isfinite(numeric).all() or numeric.lt(0).any():
        raise ValueError("Суммы переводов должны быть конечными и неотрицательными")
    node_ids = set(nodes["gid"])
    endpoints = set(edges["src"]).union(edges["dst"]).union(transactions["src"]).union(transactions["dst"])
    if not endpoints.issubset(node_ids):
        raise ValueError("В переводах есть endpoint, отсутствующий в nodes")
    aggregate = transactions.groupby(["src", "dst"], as_index=False).agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"))
    check = edges.merge(aggregate, on=["src", "dst"], how="outer", suffixes=("_edge", "_tx"), indicator=True)
    if not (check["_merge"] == "both").all():
        raise ValueError("edges и transactions расходятся по парам src/dst")
    if not np.isclose(check["sum_kzt_edge"], check["sum_kzt_tx"], rtol=1e-9, atol=0.01).all():
        raise ValueError("Суммы edges и transactions расходятся")
    if not check["n_tx_edge"].eq(check["n_tx_tx"]).all():
        raise ValueError("Счётчики n_tx в edges и transactions расходятся")
    incident = set(edges["src"]).union(edges["dst"])
    orphans = set(nodes["gid"]) - incident
    LOG.info("Данные: %d узлов, %d рёбер, %d транзакций, %d изолированных", len(nodes), len(edges), len(transactions), len(orphans))
    return orphans


def build_graph(edges: pd.DataFrame, nodes: pd.DataFrame) -> nx.DiGraph:
    """Строит DiGraph и добавляет в него в том числе изолированные gid."""
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes["gid"].astype("int64").tolist())
    for row in edges.itertuples(index=False):
        graph.add_edge(int(row.src), int(row.dst), sum_kzt=float(row.sum_kzt), n_tx=int(row.n_tx), depth=int(row.depth))
    return graph
