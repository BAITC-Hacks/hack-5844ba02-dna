"""Transaction-time signals and bounded directed cycle detection."""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd


def _fast_pass(incoming: pd.DataFrame, outgoing: pd.DataFrame, settings: dict) -> tuple[float, float]:
    """Greedily match an incoming payment to one usable, similar outgoing payment."""
    if incoming.empty or outgoing.empty:
        return 0.0, float("nan")
    used: set[int] = set()
    matched, lags = 0.0, []
    for payment in incoming.sort_values("date").itertuples():
        candidates = outgoing.loc[(outgoing.date >= payment.date) & (outgoing.date <= payment.date + pd.Timedelta(days=settings["fast_pass_max_days"]))]
        for candidate in candidates.sort_values("date").itertuples():
            if candidate.Index in used:
                continue
            if settings["fast_pass_min_ratio"] * payment.sum_kzt <= candidate.sum_kzt <= settings["fast_pass_max_ratio"] * payment.sum_kzt:
                used.add(candidate.Index)
                matched += float(payment.sum_kzt)
                lags.append((candidate.date - payment.date).days)
                break
    return matched / float(incoming.sum_kzt.sum()), float(np.median(lags)) if lags else float("nan")


def _cycles(graph: nx.DiGraph, settings: dict) -> tuple[dict[int, int], dict[int, float], list[list[str]]]:
    """Find only bounded cycles, filtering low-value reciprocal pairs."""
    counts = {int(gid): 0 for gid in graph}
    amounts = {int(gid): 0.0 for gid in graph}
    saved: list[list[str]] = []
    for cycle in nx.simple_cycles(graph, length_bound=int(settings["cycle_length_bound"])):
        values = [float(graph[source][target]["sum_kzt"]) for source, target in zip(cycle, cycle[1:] + cycle[:1])]
        if len(cycle) == 2 and min(values) < settings["cycle2_min_kzt"]:
            continue
        minimum = min(values)
        for gid in cycle:
            counts[int(gid)] += 1
            amounts[int(gid)] += minimum
        saved.append([str(int(gid)) for gid in cycle])
    return counts, amounts, saved


def add_temporal_features(graph: nx.DiGraph, features: pd.DataFrame, transactions: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list[list[str]]]:
    """Compute timing and cycle features using only the transaction ledger."""
    settings = cfg["temporal"]
    tx = transactions.copy()
    tx.date = pd.to_datetime(tx.date)
    incoming = {int(gid): group for gid, group in tx.groupby("dst", sort=False)}
    outgoing = {int(gid): group for gid, group in tx.groupby("src", sort=False)}
    daily_in = tx.groupby(["dst", "date"])["src"].nunique().groupby(level=0).max()
    daily_count = pd.concat([tx[["src", "date"]].rename(columns={"src": "gid"}), tx[["dst", "date"]].rename(columns={"dst": "gid"})]).groupby(["gid", "date"]).size()
    burst = daily_count.groupby(level=0).agg(lambda values: float(values.max() / values.mean()))
    near = pd.concat([tx[["src", "sum_kzt"]].rename(columns={"src": "gid"}), tx[["dst", "sum_kzt"]].rename(columns={"dst": "gid"})]).assign(_near=lambda frame: frame.sum_kzt.between(settings["near_threshold_min_kzt"], settings["near_threshold_max_kzt"], inclusive="left")).groupby("gid")._near.mean()
    rounded = pd.concat([tx[["src", "sum_kzt"]].rename(columns={"src": "gid"}), tx[["dst", "sum_kzt"]].rename(columns={"dst": "gid"})]).assign(_round=lambda frame: np.isclose(frame.sum_kzt % settings["round_kzt"], 0.0)).groupby("gid")._round.mean()
    fast, lag = {}, {}
    for gid in features.gid.astype(int):
        fast[gid], lag[gid] = _fast_pass(incoming.get(gid, pd.DataFrame()), outgoing.get(gid, pd.DataFrame()), settings)
    counts, amounts, saved = _cycles(graph, settings)
    result = features.copy()
    result["fast_pass_share"] = result.gid.map(fast).fillna(0.0)
    result["median_lag_days"] = result.gid.map(lag)
    result["max_sync_payers"] = result.gid.map(daily_in).fillna(0).astype(int)
    result["burst_ratio"] = result.gid.map(burst).fillna(0.0)
    result["near_threshold_share"] = result.gid.map(near).fillna(0.0)
    result["round_share"] = result.gid.map(rounded).fillna(0.0)
    result["n_cycles"] = result.gid.map(counts).fillna(0).astype(int)
    result["cycle_kzt"] = result.gid.map(amounts).fillna(0.0)
    return result, saved
