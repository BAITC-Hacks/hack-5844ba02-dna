# Money Graph viewer

An offline-first FastAPI + Cytoscape.js screen for reviewing the financial-network outputs produced by the pipeline. The viewer is deliberately limited to the MUST-HAVE scope: graph inspection, node search, node flow details, top nodes, and cluster highlighting.

## Run

```bash
make install
python scripts/make_mock_out.py  # use this until the pipeline participant supplies out/
make serve
```

Open [http://localhost:8000](http://localhost:8000). For real data, run `make pipeline` first, then start the server. `make all` runs the real pipeline and starts the server.

For the Stage 2 GPU setup and NVIDIA Brev workflow, see [docs/BREV_SETUP.md](docs/BREV_SETUP.md).

## Output contract

The API reads `out/graph.json`, `out/nodes_roles.csv`, `out/top_nodes.csv`, and `out/clusters.csv`. GIDs are kept as strings throughout Python and JavaScript because the real identifiers exceed JavaScript's safe integer range.

- `graph.json`: positioned nodes and directed, weighted edges.
- `nodes_roles.csv`: node roles, scores, metrics, evidence, flags, and score breakdown.
- `top_nodes.csv`: ranked analyst review queue.
- `clusters.csv`: cluster sizes, internal turnover, and hypotheses.

## Viewer behavior

The graph uses the supplied `x`/`y` coordinates, role colors, seed diamonds/strong borders, frontier dashed borders, priority-based node sizes, and directed arrows. Selecting a node highlights its neighborhood and loads incoming/outgoing tables. Search accepts a GID prefix or suffix. The Top and Clusters tabs link back to the graph.

## Role rules

TODO — the role rules and thresholds will be documented by participant A in the pipeline deliverable.

All conclusions are investigative hypotheses for review, not assertions of guilt.
