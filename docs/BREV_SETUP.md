# NVIDIA Brev setup guide for Money Graph

This guide explains how to use the organization’s Brev credits for Money Graph Stage 2. The current graph pipeline and viewer are CPU workloads; use the GPU for the optional Stage 2 assistant or a local NVIDIA NIM.

## 1. Choose the NVIDIA path

| Path | What it provides | Uses Brev compute credits? |
|---|---|---:|
| Brev GPU VM | Remote GPU machine with CUDA, Docker, and Jupyter | Yes |
| NVIDIA hosted API | OpenAI-compatible remote inference endpoint | No; it needs its own NVIDIA API key/quota |

For this project, use a Brev GPU VM for a local model or NIM. If the team only has `NVIDIA_API_KEY`, use the hosted NVIDIA provider instead. That key is different from Brev VM credits.

## 2. Install and authenticate Brev

Linux or WSL:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/brevdev/brev-cli/main/bin/install-latest.sh)"
brev --version
brev login
```

macOS:

```bash
brew install brevdev/homebrew-brev/brev
brev --version
brev login
```

Select the organization that received the credit balance:

```bash
brev set
```

References: [Brev CLI setup](https://docs.nvidia.com/brev/cli/getting-started), [organization selection](https://docs.nvidia.com/brev/cli/advanced-commands).

## 3. Create a GPU instance

The graph work does not need a GPU. For a small 7B/8B assistant model, start with the cheapest available GPU offering at least 16GB VRAM:

```bash
brev search --gpu-name L4 --sort price
brev create money-graph-stage2 --gpu-name L4
brev shell money-graph-stage2
nvidia-smi
```

If L4 is unavailable, choose a similar small GPU in the Brev console. Use `/home/ubuntu/workspace` for the repository. That workspace survives a stop, but deleting the instance deletes its workspace.

References: [Brev GPU instances](https://docs.nvidia.com/brev/concepts/gpu-instances), [GPU search](https://docs.nvidia.com/brev/cli/search-discovery).

## 4. Clone and run Money Graph

Inside the Brev shell:

```bash
cd /home/ubuntu/workspace
git clone <YOUR_REPOSITORY_URL> dna
cd dna
git checkout must-have-viewer
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 scripts/make_mock_out.py
python3 -m pytest -q tests/test_api.py
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

In another local terminal, forward the viewer port:

```bash
brev port-forward money-graph-stage2 --port 8000:8000
```

Open `http://localhost:8000`. Port forwarding is preferable to making a development viewer public.

Reference: [Brev connectivity](https://docs.nvidia.com/brev/cli/connectivity).

## 5. Run the real pipeline

When the pipeline participant’s code is available:

```bash
source .venv/bin/activate
make pipeline
python3 -m pytest -q tests/test_api.py
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Keep the existing contract unchanged: GIDs must remain strings in CSV, JSON, API responses, and browser JavaScript.

## 6. Use credits for the Stage 2 assistant

The recommended GPU use is a local model or NVIDIA NIM that receives structured graph facts from deterministic tools:

```text
pipeline → out/*.csv + graph.json
                 ↓
          FastAPI graph tools
                 ↓
       local model / NVIDIA NIM
                 ↓
          /api/assistant
```

For a NIM, create a VM-mode instance and verify Docker GPU access:

```bash
docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```

NIMs provide OpenAI-compatible endpoints, but the model/container must match the GPU VRAM and current support matrix. Do not put NGC, Brev, or NVIDIA API keys in git.

Reference: [Deploying NVIDIA NIMs on Brev](https://docs.nvidia.com/brev/guides/inference-deployment/deploying-nims).

## 7. Stage 2 environment variables

Create `.env` only on the Brev instance:

```dotenv
LLM_PROVIDER=nvidia
OPENAI_API_KEY=
OPENAI_MODEL=
NVIDIA_API_KEY=
NVIDIA_MODEL=meta/llama-3.1-8b-instruct
```

For the brief’s hosted NVIDIA path, `NVIDIA_API_KEY` is for `https://integrate.api.nvidia.com/v1`. For a local NIM, configure the client to use the local service URL, such as `http://127.0.0.1:8000/v1`, according to that NIM’s setup.

Start with no key and verify `llm_available: false`; the deterministic viewer must still work. Add the assistant only after Blocks A–D are complete.

## 8. Control costs

```bash
exit
brev stop money-graph-stage2
```

Stopped instances do not accrue compute charges, but storage can still consume credits. Delete the instance once the workspace is backed up:

```bash
brev delete money-graph-stage2
```

Monitor the Brev console’s balance and burn-rate indicator. Use the $50 in short sessions: setup, model experiments, demo, then stop/delete.

Reference: [Brev billing and credits](https://docs.nvidia.com/brev/guides/console-reference).

## Recommended Stage 2 order

1. Complete Blocks A–D without a model.
2. Run the API tests and suffix-search manual check after every block.
3. Use Brev GPU credits only for Block E inference.
4. Keep `llm_available=false` as a working fallback.
5. Stop or delete the instance after the demo.
