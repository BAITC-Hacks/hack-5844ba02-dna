"""Детерминированная раскладка слабосвязных компонент без наложений."""
import math
import networkx as nx
import pandas as pd


def make_layout(graph: nx.DiGraph, cfg: dict) -> pd.DataFrame:
    """Раскладывает компоненты по сетке, крупнейшую оставляя около центра."""
    weighted = graph.copy()
    for _, _, attrs in weighted.edges(data=True): attrs["layout_weight"] = math.log1p(attrs["sum_kzt"])
    components = sorted(nx.weakly_connected_components(graph), key=lambda members: (-len(members), min(members)))
    grid = math.ceil(math.sqrt(len(components)))
    scale = cfg["layout"]["scale"]; cell = scale / max(grid, 1)
    output = []
    for index, members in enumerate(components):
        subgraph = weighted.subgraph(members)
        if len(members) == 1: positions = {next(iter(members)): (0.0, 0.0)}
        else:
            try:
                positions = nx.spring_layout(subgraph, seed=cfg["seed"], weight="layout_weight", iterations=cfg["layout"]["iterations"])
            except ModuleNotFoundError:
                ordered = sorted(members)
                positions = {gid: (math.cos(2 * math.pi * offset / len(ordered)), math.sin(2 * math.pi * offset / len(ordered))) for offset, gid in enumerate(ordered)}
        row, col = divmod(index, grid)
        center_x, center_y = (col + .5) * cell, (row + .5) * cell
        radius = cell * .38
        for gid, (x, y) in positions.items(): output.append({"gid": int(gid), "x": center_x + x * radius, "y": center_y + y * radius})
    return pd.DataFrame(output)
