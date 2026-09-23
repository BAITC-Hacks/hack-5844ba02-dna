# Money Graph API

The FastAPI service reads pipeline artifacts from `out/`. All browser-facing `gid`, `id`, `source`, and `target` values are strings because identifiers exceed JavaScript's safe integer range. If the required outputs are missing or malformed, the server still starts and data endpoints return HTTP 503 with an explanation.

Interactive OpenAPI documentation is available at `http://localhost:8000/docs` while the server is running.

| Method | Path | Parameters | Returns |
|---|---|---|---|
| GET | `/api/health` | — | Service status, output availability, and optional LLM status |
| GET | `/api/summary` | — | Pipeline `summary.json`, augmented with node and seed counts when absent |
| GET | `/api/graph` | `min_kzt` optional | Positioned graph; edges below `min_kzt` are omitted |
| GET | `/api/search` | `q` | Up to 20 prefix/suffix gid matches |
| GET | `/api/node/{gid}` | string gid | Complete node record with parsed flags, score breakdown, and sorted flows |
| GET | `/api/node/{gid}/card` | string gid | Deterministic analyst card and recommended next steps |
| GET | `/api/node/{gid}/ego` | `k=1..3`, `direction=up|down|both`, `max_nodes≤300` | Bounded ego graph in graph JSON format |
| GET | `/api/path` | `src`, `dst` | Shortest directed path and edge amounts |
| POST | `/api/common` | JSON `{"gids":["..."]}` | Common senders and receivers within one or two hops, with amounts |
| GET | `/api/top` | `limit`, `role`, `cluster`, `exclude_seed` | Filtered analyst priority list |
| GET | `/api/clusters` | — | Cluster summary rows |
| GET | `/api/cluster/{id}` | integer id | Cluster members, role counts, and internal edges |
| GET | `/api/resilience` | — | Resilience JSON plus dynamically detected strategy names |
| GET | `/api/cycles` | `gid` optional | All cycles or cycles containing one gid |
| POST | `/api/reload` | — | Reloads pipeline artifacts from disk |
| POST | `/api/pipeline/run` | — | Runs the local pipeline, reloads outputs, and returns elapsed time and role counts |
| POST | `/api/assistant` | JSON `{"question":"...","history":[]}` | Tool-grounded answer, cited gids, and tool calls; 503 without a configured key |
| POST | `/api/node/{gid}/card/llm` | string gid | Narrative based only on the deterministic card; 503 without a key |

## Node response example

```json
{
  "gid": "100000003115284100",
  "id": "100000003115284100",
  "role": "coordinator",
  "role_score": 0.91,
  "cluster_id": 2,
  "priority_score": 1.0,
  "evidence": "Кандидат в координирующий узел: 8 плательщиков → 2 получателей; сигналы S3",
  "flags": ["consolidator", "S3"],
  "score_breakdown": {
    "seed_flow_kzt": 0.24,
    "n_seed_upstream": 0.18,
    "role": 0.2
  },
  "incoming": [
    {
      "gid": "100000001234567100",
      "role": "transit",
      "sum_kzt": 450000.0,
      "n_tx": 2
    }
  ],
  "outgoing": []
}
```

The example illustrates the schema only. Values returned by the running API always come from the currently loaded pipeline output.

## AI assistant configuration

Copy `.env.example` to `.env` and set either provider's key:

```bash
cp .env.example .env
```

- `LLM_PROVIDER=openai`: uses `OPENAI_API_KEY` and `OPENAI_MODEL`.
- `LLM_PROVIDER=nvidia`: uses `NVIDIA_API_KEY`, `NVIDIA_MODEL`, and `https://integrate.api.nvidia.com/v1`.

If both keys are available, an error from the selected provider triggers one attempt with the other provider. The timeout is 30 seconds per provider. The deterministic graph, cards, exports, and navigation remain available without any LLM key.
