"""In-memory, reloadable view of pipeline output files."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import networkx as nx
import pandas as pd


CORE_FILES = ("graph.json", "nodes_roles.csv", "clusters.csv", "top_nodes.csv")
NODE_OPTIONAL_COLUMNS = (
    "role",
    "role_score",
    "cluster_id",
    "priority_score",
    "evidence",
    "depth",
    "is_seed",
    "in_deg",
    "out_deg",
    "in_kzt",
    "out_kzt",
    "pass_ratio",
    "seed_flow_kzt",
    "seed_share",
    "fast_pass_share",
    "median_lag_days",
    "max_sync_payers",
    "near_threshold_share",
    "n_cycles",
    "flags",
    "score_breakdown",
)


class StoreUnavailable(RuntimeError):
    """Raised when pipeline outputs are absent or invalid."""


def _parse_scalar(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _parse_flags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        pass
    separator = ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]


def _parse_breakdown(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"raw": str(value)}


class GraphStore:
    """Load API artifacts and expose graph operations without global data copies."""

    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.loaded = False
        self.error: str | None = None
        self.graph_data: dict[str, Any] = {"nodes": [], "edges": []}
        self.nodes_by_id: dict[str, dict[str, Any]] = {}
        self.clusters: list[dict[str, Any]] = []
        self.top: list[dict[str, Any]] = []
        self.summary: dict[str, Any] = {}
        self.resilience: dict[str, Any] = {}
        self.cycles: list[list[str]] = []
        self.graph = nx.DiGraph()
        self.reload()

    def _reset(self, error: str | None = None) -> None:
        self.loaded = False
        self.error = error
        self.graph_data = {"nodes": [], "edges": []}
        self.nodes_by_id = {}
        self.clusters = []
        self.top = []
        self.summary = {}
        self.resilience = {}
        self.cycles = []
        self.graph = nx.DiGraph()

    def _read_csv(self, name: str, gid_column: str | None = None) -> list[dict[str, Any]]:
        path = self.out_dir / name
        if not path.exists():
            return []
        dtype = {gid_column: str} if gid_column else None
        frame = pd.read_csv(path, dtype=dtype, keep_default_na=False)
        rows: list[dict[str, Any]] = []
        for raw in frame.to_dict(orient="records"):
            row = {key: _parse_scalar(value) for key, value in raw.items()}
            if gid_column and row.get(gid_column) is not None:
                row[gid_column] = str(raw[gid_column])
            rows.append(row)
        return rows

    def reload(self) -> None:
        """Reload all outputs atomically; keep the server alive on failure."""
        missing = [name for name in CORE_FILES if not (self.out_dir / name).exists()]
        if missing:
            self._reset(f"Pipeline output is unavailable; missing: {', '.join(missing)}")
            return
        try:
            graph_raw = json.loads((self.out_dir / "graph.json").read_text(encoding="utf-8"))
            csv_nodes = self._read_csv("nodes_roles.csv", "gid")
            nodes_csv_by_id = {str(row["gid"]): row for row in csv_nodes if row.get("gid")}
            nodes = []
            for raw_node in graph_raw.get("nodes", []):
                gid = str(raw_node.get("id"))
                node = {**nodes_csv_by_id.get(gid, {}), **raw_node, "id": gid, "gid": gid}
                for column in NODE_OPTIONAL_COLUMNS:
                    node.setdefault(column, None)
                node["flags"] = _parse_flags(node.get("flags"))
                node["score_breakdown"] = _parse_breakdown(node.get("score_breakdown"))
                nodes.append(node)
            edges = [
                {**edge, "source": str(edge["source"]), "target": str(edge["target"])}
                for edge in graph_raw.get("edges", [])
            ]
            self.graph_data = {**graph_raw, "nodes": nodes, "edges": edges}
            self.nodes_by_id = {node["id"]: node for node in nodes}
            self.graph = nx.DiGraph()
            self.graph.add_nodes_from(self.nodes_by_id)
            for edge in edges:
                self.graph.add_edge(edge["source"], edge["target"], **edge)
            self.clusters = self._read_csv("clusters.csv")
            self.top = self._read_csv("top_nodes.csv", "gid")
            self.summary = self._read_json("summary.json", {})
            self.resilience = self._read_json("resilience.json", {})
            self.cycles = [
                [str(gid) for gid in cycle]
                for cycle in self._read_json("cycles.json", [])
                if isinstance(cycle, list)
            ]
            self.summary.setdefault("n_nodes", len(self.nodes_by_id))
            self.summary.setdefault("n_seed", sum(bool(node.get("is_seed")) for node in nodes))
            self.summary.setdefault("nodes", self.summary["n_nodes"])
            self.summary.setdefault("seeds", self.summary["n_seed"])
            self.summary.setdefault("roles", self.summary.get("role_counts", {}))
            self.loaded, self.error = True, None
        except Exception as error:  # malformed artifacts must not prevent server startup
            self._reset(f"Pipeline output could not be loaded: {error}")

    def _read_json(self, name: str, default: Any) -> Any:
        path = self.out_dir / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    def require_loaded(self) -> None:
        if not self.loaded:
            raise StoreUnavailable(self.error or "Pipeline output is unavailable")

    def graph_payload(self, min_kzt: float = 0) -> dict[str, Any]:
        self.require_loaded()
        edges = [edge for edge in self.graph_data["edges"] if float(edge.get("sum_kzt", 0)) >= min_kzt]
        return {**self.graph_data, "nodes": self.graph_data["nodes"], "edges": edges}

    def search(self, query: str) -> list[dict[str, Any]]:
        self.require_loaded()
        needle = str(query).strip()
        if not needle:
            return []
        matches = [node for gid, node in self.nodes_by_id.items() if gid.startswith(needle) or gid.endswith(needle)]
        return [
            {
                "gid": node["id"],
                "role": node.get("role"),
                "priority_score": node.get("priority_score", node.get("priority")),
                "cluster_id": node.get("cluster_id", node.get("cluster")),
            }
            for node in matches[:20]
        ]

    def node(self, gid: str) -> dict[str, Any]:
        self.require_loaded()
        gid = str(gid)
        if gid not in self.nodes_by_id:
            raise KeyError(gid)
        node = dict(self.nodes_by_id[gid])
        node["incoming"] = self._edge_rows(gid, incoming=True)
        node["outgoing"] = self._edge_rows(gid, incoming=False)
        return node

    def _edge_rows(self, gid: str, incoming: bool) -> list[dict[str, Any]]:
        edges = self.graph.in_edges(gid, data=True) if incoming else self.graph.out_edges(gid, data=True)
        rows = []
        for source, target, attrs in edges:
            other = str(source if incoming else target)
            rows.append(
                {
                    "gid": other,
                    "role": self.nodes_by_id.get(other, {}).get("role"),
                    "sum_kzt": float(attrs.get("sum_kzt", 0)),
                    "n_tx": int(attrs.get("n_tx", 0)),
                }
            )
        return sorted(rows, key=lambda row: (-row["sum_kzt"], row["gid"]))

    def top_nodes(self, limit: int, role: str | None, cluster: int | None, exclude_seed: bool) -> list[dict[str, Any]]:
        self.require_loaded()
        rows = []
        for raw in self.top:
            gid = str(raw.get("gid"))
            node = self.nodes_by_id.get(gid, {})
            row = {**raw, "gid": gid}
            row.setdefault("cluster_id", node.get("cluster_id", node.get("cluster")))
            row.setdefault("is_seed", bool(node.get("is_seed")))
            if role and row.get("role") != role:
                continue
            if cluster is not None and str(row.get("cluster_id")) != str(cluster):
                continue
            if exclude_seed and bool(row.get("is_seed")):
                continue
            rows.append(row)
        return rows[:limit]

    def cluster(self, cluster_id: int) -> dict[str, Any]:
        self.require_loaded()
        row = next((item for item in self.clusters if str(item.get("cluster_id")) == str(cluster_id)), None)
        if row is None:
            raise KeyError(str(cluster_id))
        members = [
            {"gid": node["id"], "role": node.get("role"), "priority_score": node.get("priority_score")}
            for node in self.nodes_by_id.values()
            if str(node.get("cluster_id", node.get("cluster"))) == str(cluster_id)
        ]
        member_ids = {member["gid"] for member in members}
        internal_edges = [
            edge for edge in self.graph_data["edges"]
            if edge["source"] in member_ids and edge["target"] in member_ids
        ]
        return {
            **row,
            "cluster_id": int(cluster_id),
            "nodes": sorted(members, key=lambda item: item["gid"]),
            "role_counts": dict(sorted(Counter(member["role"] for member in members).items())),
            "internal_edges": internal_edges,
        }

    def resilience_payload(self) -> dict[str, Any]:
        self.require_loaded()
        strategies = [
            key for key, value in self.resilience.items()
            if isinstance(value, dict) and {"lwcc_size", "seed_reachable"}.issubset(value)
        ]
        return {
            **self.resilience,
            "strategies": strategies,
            "removed": self.resilience.get("n_removed", []),
            "priority": self.resilience.get("by_priority", {}),
            "degree": self.resilience.get("by_degree", {}),
        }

    def cycles_for(self, gid: str | None = None) -> list[list[str]]:
        self.require_loaded()
        return [cycle for cycle in self.cycles if gid is None or str(gid) in cycle]

    def ego(self, gid: str, k: int, direction: str, max_nodes: int) -> dict[str, Any]:
        self.node(gid)
        selected = {str(gid)}
        frontier = {str(gid)}
        for _ in range(k):
            candidates = self._neighbors(frontier, direction) - selected
            ranked = sorted(candidates, key=self._incident_amount, reverse=True)
            remaining = max_nodes - len(selected)
            frontier = set(ranked[:remaining])
            selected.update(frontier)
            if not frontier or len(selected) >= max_nodes:
                break
        edges = [edge for edge in self.graph_data["edges"] if edge["source"] in selected and edge["target"] in selected]
        return {
            "center": str(gid), "k": k, "direction": direction,
            "nodes": [self.nodes_by_id[item] for item in sorted(selected)], "edges": edges,
        }

    def _neighbors(self, gids: Iterable[str], direction: str) -> set[str]:
        result: set[str] = set()
        for gid in gids:
            if direction in {"up", "both"}:
                result.update(str(item) for item in self.graph.predecessors(gid))
            if direction in {"down", "both"}:
                result.update(str(item) for item in self.graph.successors(gid))
        return result

    def _incident_amount(self, gid: str) -> float:
        outgoing = sum(float(self.graph[gid][dst].get("sum_kzt", 0)) for dst in self.graph.successors(gid))
        incoming = sum(float(self.graph[src][gid].get("sum_kzt", 0)) for src in self.graph.predecessors(gid))
        return incoming + outgoing

    def shortest_path(self, src: str, dst: str) -> dict[str, Any]:
        self.node(src)
        self.node(dst)
        try:
            gids = [str(item) for item in nx.shortest_path(self.graph, str(src), str(dst))]
        except nx.NetworkXNoPath as error:
            raise LookupError(f"Нет направленного пути от {src} до {dst}") from error
        edges = [dict(self.graph[a][b]) for a, b in zip(gids, gids[1:])]
        return {"src": str(src), "dst": str(dst), "gids": gids, "edges": edges}

    def common_counterparties(self, gids: list[str]) -> dict[str, Any]:
        normalized = [str(gid) for gid in gids]
        for gid in normalized:
            self.node(gid)
        receivers = [self._reachable_amounts(gid, "down") for gid in normalized]
        senders = [self._reachable_amounts(gid, "up") for gid in normalized]
        return {
            "gids": normalized,
            "common_receivers": self._common_rows(receivers),
            "common_senders": self._common_rows(senders),
        }

    def _reachable_amounts(self, start: str, direction: str) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        frontier = {start}
        for hop in (1, 2):
            following: set[str] = set()
            for current in frontier:
                edges = self.graph.out_edges(current, data=True) if direction == "down" else self.graph.in_edges(current, data=True)
                for source, target, attrs in edges:
                    other = str(target if direction == "down" else source)
                    if other == start:
                        continue
                    entry = found.setdefault(other, {"sum_kzt": 0.0, "hops": hop})
                    entry["sum_kzt"] += float(attrs.get("sum_kzt", 0))
                    entry["hops"] = min(entry["hops"], hop)
                    following.add(other)
            frontier = following
        return found

    def _common_rows(self, groups: list[dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        common = set.intersection(*(set(group) for group in groups)) if groups else set()
        rows = []
        for gid in common:
            rows.append(
                {
                    "gid": gid,
                    "role": self.nodes_by_id.get(gid, {}).get("role"),
                    "sum_kzt": sum(group[gid]["sum_kzt"] for group in groups),
                    "hops": max(group[gid]["hops"] for group in groups),
                }
            )
        return sorted(rows, key=lambda row: (-row["sum_kzt"], row["gid"]))
