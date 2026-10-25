# GB10 runbook: ACE Ops on NemoClaw / OpenClaw / OpenShell, local inference only

For: Tyler, at the GB10 table (Dell Pro Max with GB10, DGX OS, ARM64, 128 GB unified memory).
Written 2026-10-25 against the NemoClaw docs "latest", NemoClaw `lkg` = **v0.0.137** (2026-10-20),
the OpenClaw **2026.9.2** that NemoClaw bakes into its sandbox image, and the OpenShell **0.0.116** that
NemoClaw pins. Config files referenced here are in `src/sdlc/runtime/`.

Labels used below:
- **Verified**: checked in official docs or source, or tested on a Mac with the repo's own MCP SDK.
- **Unverified**: could not be checked without the GB10. Watch these steps.
- **Preview/Experimental**: the vendor itself labels it that way.

---

## 0. Read this first

### The stack in one minute

| Piece | What it is | Install on GB10 |
|---|---|---|
| **OpenShell** (NVIDIA) | The sandbox runtime: gateway + per-sandbox supervisor; Landlock/seccomp/netns isolation; an L7 egress proxy that is **deny-by-default**; credentials kept outside the sandbox. CLI `openshell` (`openshell term` = live TUI of network activity). | Installed **by NemoClaw** (pinned 0.0.116). Do not install or self-update it separately on a NemoClaw box ([prerequisites](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/get-started/prerequisites)). Standalone installer for reference only: `curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh \| sh` ([README](https://github.com/NVIDIA/OpenShell)). |
| **OpenClaw** | The agent: gateway, TUI, web dashboard, tools, MCP client, chat channels. Config lives in `/sandbox/.openclaw/openclaw.json` inside the sandbox. | Installed **by NemoClaw** inside the sandbox image (OpenClaw 2026.9.2). |
| **NemoClaw** (NVIDIA) | The reference stack on the host: `nemoclaw` CLI that installs OpenShell, builds a hardened OpenClaw sandbox, wires local inference, applies network policy presets, manages MCP servers and channels. Apache-2.0. | `curl -fsSL https://www.nvidia.com/nemoclaw.sh \| bash` ([quickstart](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/get-started/quickstart)). |

**Preview caveats:** NemoClaw is pre-1.0 (`v0.0.x`; a `v1.0.0-rc1` tag exists). Several paths we mention
are labelled Experimental or Deferred by NVIDIA (managed llama.cpp, Local NIM, two-Spark vLLM, some
Ollama/NIM profiles). The path below uses the docs' default local option (Ollama).

### Three facts that shape this runbook

1. **A sandbox cannot reach host loopback.** Our servers bind `127.0.0.1` only (hard-coded in
   `src/intake/config.py`, `src/board/__main__.py`, `src/sdlc/__main__.py`). NemoClaw docs: "Sandbox loopback is
   not the host service" ([add MCP server](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/manage-sandboxes/mcp-servers/add-an-mcp-server)).
   The documented route to a host service is: expose it on a host IP that OpenShell can reach, then allow
   that IP and port with a custom policy preset ([troubleshooting: host-side HTTP service](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/troubleshooting#agent-cannot-reach-a-host-side-http-service)).
   We do that with a small Caddy reverse proxy bound **only** to the `openshell-docker` bridge IP, which
   is what `host.openshell.internal` resolves to inside the sandbox.
2. **The MCP Python SDK rejects foreign Host headers.** When a server binds 127.0.0.1, `mcp` 2.3.0 turns on
   DNS-rebinding protection and only accepts `Host: 127.0.0.1:*|localhost:*|[::1]:*`. **Verified** on a Mac
   with the repo's venv: `Host: host.openshell.internal:28791` → `421 Invalid Host header`;
   `Host: 127.0.0.1:8791` → `200`. So the proxy must rewrite Host (Caddy does, see `Caddyfile.mcp-bridge`).
3. **NemoClaw's managed `nemoclaw <sb> mcp add` will not take our servers as they are.** It requires
   **HTTPS**, rejects loopback and `host.openshell.internal`, and needs exactly one bearer credential per server.
   A private HTTPS endpoint also needs a CA that you bake into the sandbox ([add MCP server](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/manage-sandboxes/mcp-servers/add-an-mcp-server),
   [troubleshoot MCP](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/troubleshoot-mcp-servers)).
   The fast path today is therefore **agent-native registration**: `openclaw mcp set` inside the sandbox,
   plus our custom policy preset. The docs name this path ("editing OpenClaw `openclaw.json` inside the
   sandbox, may accept a plain-HTTP or local URL"), and note that it bypasses NemoClaw's credential
   replacement. The managed route is Appendix B (optional).

### Time plan (rough)

| Step | Time |
|---|---|
| 1 Prereqs | 5 min |
| 2 Ollama + model pulls (about 29 GB) | 10 to 25 min, network-bound |
| 3 to 4 Repo + `make demo` | 10 min |
| 5 NemoClaw install + onboard (sandbox image about 2.4 GB compressed) | 15 to 30 min |
| 6 MCP bridge + registration | 15 min |
| 7 to 8 Lock egress + proof rehearsal | 15 min |

**Go/no-go:** if section 6 is not working 45 minutes before judging, use Appendix C as the fallback,
and declare only what you actually run.

### Shell variables used everywhere (bash; paste once per terminal)

```bash
export SB=aceops                       # our sandbox name (use my-assistant if you reuse an existing one)
export REPO=~/aceops                   # repo location on the GB10
export OC_MODEL=nemotron-3-nano:30b    # OpenClaw's model (tool calling)
export APP_MODEL=llama3.1:8b           # client/internal agent model (short JSON, non-thinking)
export NEMOCLAW_DISABLE_TELEMETRY=1    # NemoClaw installer/CLI telemetry off (docs: best-practices#operation-telemetry)
export INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'   # MCP initialize probe body
```

`BRIDGE_IP` (6.1) and `INTAKE_TOKEN` (6.3) are set later. Run sections 6.1 to 6.6 in **one** terminal, or re-export them.

Telemetry source: [NemoClaw security best practices, Operation Telemetry](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/security/best-practices#operation-telemetry).
Persist it: `echo 'export NEMOCLAW_DISABLE_TELEMETRY=1' >> ~/.bashrc`.

---

## 1. Prereqs and checks

```bash
uname -m                                   # expect aarch64
. /etc/os-release && echo "$PRETTY_NAME"   # DGX OS 7 is Ubuntu 24.04 based
nvidia-smi                                 # GB10 listed. "Memory-Usage: Not Supported" is NORMAL on GB10
free -g && df -h ~                         # want 60+ GB free disk for images + models
docker info >/dev/null && echo docker-ok   # if permission denied: sudo usermod -aG docker $USER && newgrp docker
command -v nemoclaw openshell ollama uv caddy make git || true
nemoclaw --version 2>/dev/null; nemoclaw list 2>/dev/null
ollama --version 2>/dev/null; ollama list 2>/dev/null
sudo ss -ltnp | grep -E ':(8000|8080|8787|8788|8790|8791|8792|11434|11435|18789|28787|28791)\b' || echo "ports free"
env | grep -E -i '(OPENAI|ANTHROPIC|OPENROUTER|GEMINI|NVIDIA_INFERENCE|NVIDIA_API|COMPATIBLE)[A-Z_]*KEY' | sed 's/=.*/=<set>/'
```

- `Memory-Usage: Not Supported` is expected on GB10 because there is no dedicated framebuffer; per-process memory is still listed ([DGX Spark known issues](https://docs.nvidia.com/dgx/dgx-spark/known-issues.html)).
- Ports: 8080 is the OpenShell gateway default and 18789 to 18799 is the OpenClaw dashboard range (NemoClaw `src/lib/core/protected-host-ports.ts`). Our bridge ports 28787 and 28791 avoid both ranges.
- If any cloud API key is printed, `unset` it in every shell you use for the demo. The hackathon forbids remote LLM calls.
- **If NemoClaw is already installed** (NVIDIA staff may have run Express): run `nemoclaw <name> status`.
  If its Inference line shows a hosted provider (NVIDIA Endpoints, OpenAI, and so on), do not use that sandbox; create ours in section 5.
  If it shows Local vLLM, you may reuse it (section 2B), but still make our own `aceops` sandbox with Ollama unless you are short on time.
- **Unverified:** whether NemoClaw classifies a *Dell Pro Max with GB10* as "DGX Spark". It does not decide by GPU name alone ([quickstart starter prompt rules](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/get-started/quickstart)).
  If it does not, Express and managed vLLM are not offered. The Ollama path below is unaffected.

Get the repo onto the box **without** the Mac `.venv` (macOS binaries) or `data/`:

```bash
# from the Mac, in the aceops folder (or git clone your team remote on the GB10 instead)
rsync -a --exclude .venv --exclude data --exclude .env --exclude __pycache__ ./ <user>@<gb10-host>:~/aceops/
```

---

## 2. Serve the local model

### 2A. Ollama (recommended path)

Why Ollama: it is NemoClaw's default local option. NemoClaw keeps Ollama on `127.0.0.1:11434` and puts its own token-gated proxy on `0.0.0.0:11435` for the sandbox. Our host apps call `127.0.0.1:11434` directly with no key. No NGC login is needed.
Sources: [Set Up Ollama](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/inference/local-inference/set-up-ollama), [Ollama Linux](https://docs.ollama.com/linux).

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama --version            # NemoClaw needs >= 0.32.9 (older versions return tool calls as text)
# only if lower than 0.32.9:
curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION=0.32.9 sh
sudo ss -ltnp | grep 11434  # must be 127.0.0.1:11434 only (NemoClaw requires loopback; do NOT set OLLAMA_HOST=0.0.0.0)
ollama pull "$OC_MODEL"     # nemotron-3-nano:30b, about 24 GB (tools + thinking)
ollama pull "$APP_MODEL"    # llama3.1:8b, about 4.9 GB (tools, no thinking)
ollama list
```

Never pick a `:cloud` or `-cloud` tag (for example `nemotron-3-nano:30b-cloud`). Those are remote inference.

**Tool-calling test (OpenAI-compatible, the shape OpenClaw uses):**

```bash
curl -s http://127.0.0.1:11434/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "nemotron-3-nano:30b",
  "messages": [{"role": "user", "content": "What is the weather in Austin? Use the tool."}],
  "tools": [{"type": "function", "function": {"name": "get_weather",
    "description": "Get current weather for a city",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
}' | python3 -c 'import json,sys; m=json.load(sys.stdin)["choices"][0]["message"]; print(json.dumps(m.get("tool_calls") or m, indent=2))'
```

Pass: a `tool_calls` list with `"name": "get_weather"` and arguments containing Austin. Fail: plain text with JSON in it. In that case, upgrade Ollama or switch `OC_MODEL` to `qwen3.6:35b` (NemoClaw's default Ollama starter, about 24 GB).
`tool_choice` is not supported by Ollama's OpenAI endpoint ([Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)).

**Keep both models loaded** (a cold load can exceed the client agent's 20 s timeout) ([Ollama FAQ](https://docs.ollama.com/faq)):

```bash
curl -s http://127.0.0.1:11434/api/generate -d '{"model":"llama3.1:8b","keep_alive":-1}' >/dev/null
curl -s http://127.0.0.1:11434/api/generate -d '{"model":"nemotron-3-nano:30b","keep_alive":-1}' >/dev/null
ollama ps                   # PROCESSOR column should read 100% GPU
```

NemoClaw unloads **every** loaded Ollama model when you stop or destroy an Ollama-backed sandbox ([Set Up Ollama, Release GPU Memory](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/inference/local-inference/set-up-ollama)). Re-run the two `keep_alive` lines after any `nemoclaw ... stop`.

### Models NVIDIA points to for Spark-class boxes (approximate download sizes)

| Model | Where NVIDIA recommends it | Size | Notes |
|---|---|---|---|
| `nemotron-3-nano:30b` (Ollama) | NemoClaw Ollama starter list ([Spark playbook](https://build.nvidia.com/spark/nemoclaw/instructions)) | 24 GB | Tools + thinking. Our OpenClaw default. |
| `qwen3.6:35b` (Ollama) | NemoClaw's default Ollama starter when memory allows | 24 GB | Fallback if Nemotron fails NemoClaw's tool-call validation |
| `nvidia/Qwen3.6-35B-A3B-NVFP4` (managed vLLM) | NemoClaw Express default on DGX Spark, QA'd on 128 GB ([Set Up vLLM](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/inference/local-inference/set-up-vllm)) | 9.6 GB image + weights | Pulls from `nvcr.io` (NGC login) |
| `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4` | Explicit opt-in vLLM profile (Experimental); Spark NIM playbook default ([NIM on Spark](https://build.nvidia.com/spark/nim-llm/instructions)) | 21.6 GB weights | Reasoning model |
| Nemotron 3 Nano 30B-A3B GGUF | NemoClaw managed llama.cpp recipe on Spark (Experimental) ([Set Up llama.cpp](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/inference/local-inference/set-up-llama-cpp)) | n/a | |
| `nemotron-3-super:120b` (Ollama) | Ollama library | 87 GB | Fits, but leaves little headroom on 128 GB. Not with other models. |
| `llama3.1:8b` (Ollama) | Ollama library | 4.9 GB | Our app model: fast, no thinking |

Runtime memory is weights plus KV cache. On GB10 Ollama defaults to 256k context because it sees 48 GB or more ([Ollama context length](https://docs.ollama.com/context-length)). Unified memory is shared with the OS, so do not run managed vLLM and large Ollama models at the same time ([vLLM warning about Spark freezes](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/inference/local-inference/set-up-vllm)).

### 2B. Alternatives (only if Ollama is blocked or already replaced)

- **Reuse an Express managed vLLM** (`nemoclaw-vllm` container on `127.0.0.1:8000`):
  ```bash
  curl -s http://127.0.0.1:8000/v1/models | python3 -m json.tool
  # if 401, the bearer is the host-global key NemoClaw stores for authenticated managed vLLM profiles:
  curl -s -H "Authorization: Bearer $(cat ~/.nemoclaw/dual-station-vllm-api-key)" http://127.0.0.1:8000/v1/models
  ```
  Key path source: [Host Files and State](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/host-files-and-state). **Unverified** whether the Spark default profile is the authenticated one, so try without the key first.
  Put `LLM_BASE_URL=http://127.0.0.1:8000/v1`, the model `id` and the key in `.env` (gitignored).
  Qwen3.6 is a thinking model, so the client agent's 200-token budget may be spent on reasoning (section 3.3 catches this). Keep `llama3.1:8b` in Ollama for the app if so.
- **Operator-run NIM, Nemotron 3.5 Lightning** (needs an NGC API key). The command comes from the [Spark NIM playbook](https://build.nvidia.com/spark/nim-llm/instructions), with the port bound to loopback (the playbook uses `-p 8000:8000`, which exposes it to the LAN):
  ```bash
  echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin
  docker run -d --name nim-llm-demo --gpus all --shm-size=16GB \
    -e NGC_API_KEY=$NGC_API_KEY \
    -e NIM_MODEL_NAME=nvidia/nemotron-3.5-lightning-30b-a3b \
    -e NIM_SERVED_MODEL_NAME=nvidia/nemotron-3.5-lightning-30b-a3b \
    -e NIM_PASSTHROUGH_ARGS="--reasoning-parser nemotron_v3" \
    -v ~/.cache/nim:/opt/nim/.cache -v ~/.local/share/nim/workspace:/opt/nim/workspace \
    -p 127.0.0.1:8000:8000 nvcr.io/nim/nvidia/nemotron-3.5-lightning-30b-a3b:latest
  ```
  Then use NemoClaw provider "Other OpenAI-compatible endpoint" at `http://127.0.0.1:8000/v1` with no auth. Per the docs, a no-auth loopback endpoint on port 8000 is fronted by NemoClaw's protected proxy and must stay loopback-only ([quickstart](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/get-started/quickstart), [troubleshooting](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/troubleshooting#ollama-auth-proxy-did-not-start)). **Not tested by us.**
- **llama.cpp**: [Spark llama.cpp playbook](https://build.nvidia.com/spark/llama-cpp/instructions) (build with `-DCMAKE_CUDA_ARCHITECTURES=121a-real`; `--chat-template-kwargs '{"enable_thinking": false}'` would stop Qwen thinking server-wide). NemoClaw expects an *authenticated* llama.cpp on loopback port 8081 for its existing-server path. More moving parts; skip today.

---

## 3. Configure the repo

### 3.1 Python env

```bash
cd "$REPO"
command -v uv || { curl -LsSf https://astral.sh/uv/install.sh | sh && source "$HOME/.local/bin/env"; }
command -v make || sudo apt-get install -y make
uv sync                      # creates .venv for Python 3.12 (ARM64 wheels)
```

uv install source: [docs.astral.sh/uv installation](https://docs.astral.sh/uv/getting-started/installation/).

### 3.2 `.env`

```bash
cd "$REPO"
test -f .env && cp .env ".env.bak.$(date +%s)"
cp src/sdlc/runtime/gb10.env.example .env
sed -i "s/^ADMIN_TOKEN=.*/ADMIN_TOKEN=$(openssl rand -hex 32)/" .env
chmod 600 .env
grep -E '^(LLM_|INTERNAL_LLM_|SDLC_)' .env
```

Important behaviour (from `scripts/run_demo.sh`): it **exports every key in `.env` and overrides your shell**. Set model values in `.env`, not with `export`. `DEMO_MODE` is deliberately not in `.env`, so `DEMO_MODE=scripted make demo` still works.

Loopback guard (prints NOT LOCAL if any model URL would leave the box):

```bash
cd "$REPO" && .venv/bin/python - <<'PY'
from urllib.parse import urlparse
env = {}
for raw in open(".env", encoding="utf-8").read().splitlines():
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); env[k.strip()] = v.strip()
for k in ("LLM_BASE_URL", "INTERNAL_LLM_BASE_URL", "SDLC_LLM_BASE_URL"):
    v = env.get(k, "")
    host = urlparse(v).hostname if v else None
    print(f"{k:24} {v or '(unset)':40} {'OK' if not v or host in ('127.0.0.1', 'localhost', '::1') else 'NOT LOCAL'}")
PY
```

### 3.3 Smoke test the app's exact model call

This uses the repo's own `LocalLLM`, prompt builder and validator from `src/intake/client_agent.py`, so it tests what `make demo` will do: max_tokens 200, temperature 0, 20 s timeout, bare-JSON answer.

```bash
cd "$REPO" && PYTHONPATH=src .venv/bin/python - <<'PY'
import os, time
from pathlib import Path
from intake.config import load_dotenv
load_dotenv(Path(".env"))
from intake.client_agent import LocalLLM, _prompt, validate_answer
llm = LocalLLM(os.environ["LLM_BASE_URL"], os.environ["LLM_MODEL"], os.environ.get("LLM_API_KEY", ""))
item = {"id": "P1", "text": "What is your target ROAS?", "why": "Sets bid targets."}
t = time.time()
raw = llm.complete(_prompt(item, {"status": "PROVIDED", "value": "4.0 blended ROAS"}))
print(f"{os.environ['LLM_MODEL']}: {time.time() - t:.1f}s (client timeout is 20 s)")
print("raw:", repr(raw[:300]))
print("valid:", validate_answer(raw))
llm.close()
PY
```

Pass: `valid: {'status': 'PROVIDED', 'value': '4.0 blended ROAS', 'reason_if_na': ''}` in well under 20 s.
If `raw` is empty, has `<think>`, or is fenced in backticks, the model is not usable for the client agent: keep `LLM_MODEL=llama3.1:8b`.
Try `LLM_MODEL=nemotron-3-nano:30b` only if this test passes with it.

---

## 4. Start the app

```bash
cd "$REPO"
DEMO_MODE=scripted make demo     # rehearsal, no model. Must end with the file/board match table, all "yes"
make demo-stop
make demo                        # real run: client agent uses LLM_* and must print "mode: llm"
grep '^mode:' data/logs/client.log
```

`make demo` leaves intake (8787/8788), the board (8790) and the live BRD loop running after it exits (they are started with `setsid`). Keep them running for section 6. Stop everything with `make demo-stop`. Board: http://127.0.0.1:8790 (browser on the GB10, or `ssh -L 8790:127.0.0.1:8790` from a laptop).

**SDLC service (SDLC lane).** The entrypoint is in `src/sdlc/__main__.py`. It needs `PYTHONPATH=src` (**verified**: without it, `python -m sdlc` fails with "No module named sdlc"). Confirm the flags with the SDLC lane before the demo:

```bash
cd "$REPO"
PYTHONPATH=src nohup .venv/bin/python -m sdlc > data/logs/sdlc.log 2>&1 &   # = the lane's `uv run python -m sdlc`; live data (data/out)
# or, for a demo that does not depend on intake: PYTHONPATH=src nohup .venv/bin/python -m sdlc --source sample > data/logs/sdlc.log 2>&1 &
echo $! > data/sdlc.pid
sleep 3; head -5 data/logs/sdlc.log   # "sdlc: model llama3.1:8b at http://127.0.0.1:11434/v1", console :8792, MCP :8791
# stop: kill "$(cat data/sdlc.pid)"
```

Keep the SDLC PID in its own file, **not** in `data/demo.pids`: every `make demo` starts by killing every PID in `data/demo.pids` (`stop_demo` in `scripts/run_demo.sh`). With its own file, SDLC (and Caddy in 6.2) survive re-runs of `make demo`.

The SDLC service refuses to start if its model URL is not loopback (`src/sdlc/config.py`), and its MCP tool list has no approval tools (`src/sdlc/mcp_server.py`).

Check both MCP servers on loopback (`initialize` payload **verified** against the same SDK on a Mac):

```bash
curl -sS -m 5 -X POST http://127.0.0.1:8791/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d "$INIT"; echo
curl -sS -m 5 -X POST http://127.0.0.1:8787/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d "$INIT" -w ' HTTP %{http_code}\n'   # 401 without a token = correct
```

Always pass `-m` to curl: a plain `GET /mcp` opens an SSE stream that never ends.

---

## 5. Install and onboard NemoClaw (installs OpenShell + OpenClaw)

### 5.1 Interactive (recommended, you see every prompt)

```bash
export NEMOCLAW_DISABLE_TELEMETRY=1
export OPENSHELL_TELEMETRY_ENABLED=false   # Unverified: documented for the OpenShell gateway; not documented whether NemoClaw's gateway inherits it
curl -fsSL https://www.nvidia.com/nemoclaw.sh | NEMOCLAW_NO_EXPRESS=1 bash
```

Answer the wizard like this ([quickstart](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/get-started/quickstart)):

| Prompt | Answer |
|---|---|
| Third-party software notice | accept |
| Agent | **OpenClaw** |
| Inference provider | **8) Local Ollama (localhost:11434)**. Never 1 to 7 or 9: those are hosted. |
| Model | `nemotron-3-nano:30b` |
| Review configuration | 1) Apply |
| Sandbox name | `aceops` |
| Web search | skip / none |
| Messaging channels | none (press Enter) |
| Network policy tier | **Restricted** (baseline only; no npm/pypi/huggingface presets, no `openclaw-pricing`) |

Open a new shell afterwards (or `source ~/.bashrc`) so `nemoclaw` and Node are on `PATH`.

### 5.2 Non-interactive alternative (same choices; all variables documented)

```bash
curl -fsSL https://www.nvidia.com/nemoclaw.sh | \
  NEMOCLAW_NON_INTERACTIVE=1 NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1 NEMOCLAW_YES=1 \
  NEMOCLAW_AGENT=openclaw NEMOCLAW_PROVIDER=ollama NEMOCLAW_MODEL=nemotron-3-nano:30b \
  NEMOCLAW_SANDBOX_NAME=aceops NEMOCLAW_POLICY_TIER=restricted \
  NEMOCLAW_WEB_SEARCH_PROVIDER=none NEMOCLAW_AGENT_HEARTBEAT_EVERY=0m \
  NEMOCLAW_DISABLE_TELEMETRY=1 bash
# if the CLI is already installed:
NEMOCLAW_PROVIDER=ollama NEMOCLAW_MODEL=nemotron-3-nano:30b NEMOCLAW_POLICY_TIER=restricted \
  NEMOCLAW_WEB_SEARCH_PROVIDER=none NEMOCLAW_AGENT_HEARTBEAT_EVERY=0m \
  nemoclaw onboard --name aceops --non-interactive --yes --yes-i-accept-third-party-software
```

Variables are from the [commands reference, Onboarding Configuration](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/commands), the [Ollama page](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/inference/local-inference/set-up-ollama) and [Network Policies tiers](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/network-policies). Keep the variables on the `bash` side of the pipe. `NEMOCLAW_AGENT_HEARTBEAT_EVERY=0m` turns off periodic agent turns so the GPU graph only moves when we act.

### 5.3 Verify

```bash
nemoclaw "$SB" status          # Inference: healthy; Agent: OpenClaw v2026.9.x; provider Local Ollama
nemoclaw "$SB" inference get   # provider ollama-local, model nemotron-3-nano:30b
nemoclaw "$SB" exec -- openclaw agent --agent main -m "Reply with the single word ready."
```

- Inference not healthy under Restricted? Run `nemoclaw "$SB" policy add local-inference --yes` (NemoClaw's built-in preset for host Ollama/vLLM through `host.openshell.internal`), then check status again. **Unverified** whether Restricted needs it; the native Ollama provider attachment should carry its own route.
- Onboarding stopped with `missing structured tool call`? Run `ollama pull qwen3.6:35b`, then `NEMOCLAW_MODEL=qwen3.6:35b nemoclaw onboard --resume` (or `--fresh`).
- Web UI: `nemoclaw "$SB" dashboard-url --quiet` prints a tokenized URL. Treat it as a password. TUI: `nemoclaw "$SB" connect`, then `openclaw tui`.

---

## 6. Register our MCP servers (agent-native path)

Route: OpenClaw (in sandbox) → OpenShell proxy (policy check) → `host.openshell.internal:28787|28791` (bridge IP) → Caddy → `127.0.0.1:8787|8791/mcp`.

### 6.1 Find the bridge IP

```bash
BRIDGE_IP=$(nemoclaw "$SB" exec --no-stdin -- getent hosts host.openshell.internal | awk '{print $1; exit}')
echo "sandbox sees host.openshell.internal = $BRIDGE_IP"
docker network inspect openshell-docker --format '{{(index .IPAM.Config 0).Gateway}}'   # usually the same, e.g. 172.18.0.1
ip -br -4 addr | grep -w "$BRIDGE_IP"     # MUST print a host interface (a br-xxxx bridge)
```

Sources: `getent` check and the `openshell-docker` network ([troubleshooting](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/troubleshooting)); "private IPv4 gateway of the openshell-docker bridge, such as 172.18.0.1" ([choose a local inference server](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/inference/local-inference/choose-local-inference-server)).
If the IP is not a host interface, use the `openshell-docker` gateway IP from the second command instead (**Unverified** fallback). If the network is recreated (fresh onboard), the IP can change: redo 6.1 to 6.2.

### 6.2 Run the Caddy bridge

```bash
sudo apt-get update && sudo apt-get install -y caddy
sudo systemctl disable --now caddy        # the package starts a default site on :80; we don't want it
cd "$REPO" && mkdir -p data/logs
export BRIDGE_IP
caddy validate --config src/sdlc/runtime/Caddyfile.mcp-bridge --adapter caddyfile
nohup caddy run --config src/sdlc/runtime/Caddyfile.mcp-bridge --adapter caddyfile > data/logs/caddy-mcp-bridge.log 2>&1 &
echo $! > data/caddy.pid                  # own PID file, so `make demo` does not kill it. Stop: kill "$(cat data/caddy.pid)"
sudo ss -ltnp | grep -E ':(28787|28791)\b'   # must show $BRIDGE_IP:28787 and :28791, NOT 0.0.0.0
```

If a host firewall is active (`sudo ufw status` reports `Status: active`), allow only the sandbox subnet. This is the same pattern NemoClaw documents for its Ollama proxy ([Set Up Ollama](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/inference/local-inference/set-up-ollama)):

```bash
SUBNET=$(docker network inspect openshell-docker --format '{{(index .IPAM.Config 0).Subnet}}')
sudo ufw allow from "$SUBNET" to any port 28787 proto tcp
sudo ufw allow from "$SUBNET" to any port 28791 proto tcp
```

Host-side test through the bridge (proves the Host rewrite):

```bash
curl -sS -m 5 -X POST "http://$BRIDGE_IP:28791/mcp" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d "$INIT"; echo
# expect {"jsonrpc":"2.0","id":1,"result":{... "serverInfo":{"name":"ACE Ops SDLC" ...}}}.  "Invalid Host header" (421) = Host not rewritten.
```

### 6.3 An intake invitation token for OpenClaw

The intake MCP requires a per-client bearer (invitation) token (`src/intake/server.py`). `make demo` deletes its own token after use, so create a client for OpenClaw. To have that client drive the **live board**, use Appendix A instead.

```bash
cd "$REPO"
ADMIN_TOKEN=$(grep '^ADMIN_TOKEN=' .env | cut -d= -f2-)
curl -fsS -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  http://127.0.0.1:8788/admin/clients > data/.openclaw-client.json && chmod 600 data/.openclaw-client.json
INTAKE_TOKEN=$(python3 -c 'import json;print(json.load(open("data/.openclaw-client.json"))["invitation_token"])')
curl -sS -m 5 -X POST "http://$BRIDGE_IP:28787/mcp" -H "Authorization: Bearer $INTAKE_TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d "$INIT"; echo
```

### 6.4 Allow exactly those two endpoints in the sandbox policy

```bash
cd "$REPO"
nemoclaw "$SB" policy add --from-file src/sdlc/runtime/aceops-mcp-bridge.yaml --dry-run   # read the preview
nemoclaw "$SB" policy add --from-file src/sdlc/runtime/aceops-mcp-bridge.yaml --yes
nemoclaw "$SB" policy list                                                                 # shows aceops-mcp-bridge [user-added]
```

The preset **validates against NemoClaw v0.0.137's `policy-preset.schema.json`** (checked offline). `allowed_ips` is accepted only because the host is `host.openshell.internal` (NemoClaw `src/lib/policy/index.ts`).
Docs: [create custom presets](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/network-policy/configure-policies/create-custom-policy-presets), [`policy add` reference](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/commands).

From inside the sandbox (the preset also allows `/usr/bin/curl` for this test):

```bash
nemoclaw "$SB" exec --no-stdin -- curl -sS -m 10 -X POST http://host.openshell.internal:28791/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d "$INIT"; echo
```

Got `policy_denied` or `CONNECT tunnel failed, response 403`? Open `openshell term` and read the denied request's binary path. Add that path to `binaries:` and re-apply. Got `upstream_unreachable`? The policy matched but Caddy is not reachable: check the bind IP and ufw ([troubleshooting](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/troubleshooting#agent-cannot-reach-a-host-side-http-service)).

### 6.5 Register the servers in OpenClaw

The format is `openclaw mcp set <name> <json>`, with `url`, `transport: "streamable-http"` and optional `headers`. **Verified** in the OpenClaw 2026.9.2 docs shipped in the npm package and at [docs.openclaw.ai/cli/mcp/transports](https://docs.openclaw.ai/cli/mcp/transports). Without `transport`, OpenClaw assumes SSE.

```bash
cd "$REPO"
nemoclaw "$SB" exec --no-stdin -- openclaw mcp set aceops-sdlc \
  "$(python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1]))))' src/sdlc/runtime/openclaw-mcp-aceops-sdlc.json)"
nemoclaw "$SB" exec --no-stdin -- openclaw mcp set aceops-intake \
  "$(sed "s/__INTAKE_INVITATION_TOKEN__/$INTAKE_TOKEN/" src/sdlc/runtime/openclaw-mcp-aceops-intake.json | python3 -c 'import json,sys;print(json.dumps(json.load(sys.stdin)))')"
nemoclaw "$SB" gateway restart
nemoclaw "$SB" exec --no-stdin -- openclaw mcp status --verbose
nemoclaw "$SB" exec --no-stdin -- openclaw mcp doctor aceops-sdlc --probe
nemoclaw "$SB" exec --no-stdin -- openclaw mcp doctor aceops-intake --probe
```

`doctor` warns that the intake header holds a literal bearer. That is expected: it is a per-demo invitation token, and OpenClaw redacts it in logs.
Before any `nemoclaw "$SB" rebuild` (which refuses credential-bearing home content), run `nemoclaw "$SB" exec -- openclaw mcp unset aceops-intake` ([rebuild reference](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/commands)).

**Unverified (the biggest risk in this runbook):** that OpenClaw's built-in MCP HTTP client sends plain-HTTP traffic to `host.openshell.internal` through the sandbox proxy the same way OpenClaw's Ollama memory-search provider does in NVIDIA's [memory-search guide](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/configure-agents/configure-memory-search). That guide uses the same `host.openshell.internal:<port>` pattern. If `doctor --probe` fails while the in-sandbox curl in 6.4 works, check `openshell term` for the denied binary first, then use Appendix C.

### 6.6 Drive it

```bash
nemoclaw "$SB" exec --no-stdin -- openclaw agent --agent main -m \
  "Use the aceops-sdlc MCP tools. Call build_status, then list_specs. Summarise in 4 bullets which specs wait on the project owner and which client gaps block work. Do not invent data."
```

For the intake demo, use `nemoclaw "$SB" connect` then `openclaw tui`, and prompt:
"You are the AI assistant for Northline Goods. Use the aceops-intake tools: call get_next_item, ask me that question, then submit my answer with submit_answer (answered_by client_ai, client_ai_name OpenClaw). Repeat three times, then call get_progress."
OpenClaw may ask you to approve tool use; approve in the TUI. (**Unverified**: NemoClaw's default tool-approval posture for MCP tools.)

---

## 7. Lock egress

NemoClaw is deny-by-default. Restricted tier adds nothing beyond the baseline ([Network Policies](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/network-policies)). The OpenClaw baseline still allows `integrate.api.nvidia.com`, `clawhub.ai`, `openclaw.ai`/`catalog.openclaw.ai`, `docs.openclaw.ai` and `registry.npmjs.org` for specific binaries. To show "local and our two MCP endpoints only", exclude those baseline keys. All five are excludable for OpenClaw (NemoClaw `src/lib/policy/baseline-exclusion.ts`); `managed_inference` cannot be excluded and stays.

```bash
for k in nvidia clawhub openclaw_api openclaw_docs npm_registry; do nemoclaw "$SB" policy exclude "$k" --dry-run; done
# after reading the previews (plugin install/discovery and docs lookups stop working, which is fine today):
for k in nvidia clawhub openclaw_api openclaw_docs npm_registry; do nemoclaw "$SB" policy exclude "$k" --force; done
nemoclaw "$SB" policy list
nemoclaw "$SB" policy get > "$REPO/data/live-policy.yaml"     # the live policy to show judges (credentials stripped)
```

Undo one with `nemoclaw "$SB" policy restore <key> --force` ([policy exclude/restore](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/commands)).

**Show it in the demo** (second terminal: `openshell term`, select the sandbox, press `r` for Network Rules):

```bash
nemoclaw "$SB" exec --no-stdin -- curl -sS -m 10 -o /dev/null -w '%{http_code}\n' https://api.openai.com/v1/models   # expect a failure / 403
nemoclaw "$SB" exec --no-stdin -- curl -sS -m 10 -o /dev/null -w '%{http_code}\n' http://host.openshell.internal:8792/  # SDLC console: denied (the agent cannot reach the approval API)
nemoclaw "$SB" exec --no-stdin -- curl -sS -m 10 -o /dev/null -w '%{http_code}\n' http://host.openshell.internal:28791/mcp -X POST \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d "$INIT"                  # allowed: 200
```

Denied requests show up in `openshell term` as pending rules. **Never press `a` / `A` (approve) during the demo**; press `x` to reject ([approve or deny requests](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/network-policy/approve-network-requests)). The exact curl error text for a denied CONNECT is **Unverified**; the docs show `CONNECT tunnel failed, response 403`.

Host side: the sandbox policy does not govern host processes (Ollama, Docker, the NemoClaw CLI). Section 8 proves those stay quiet too. Do not pull images or models during the demo.

---

## 8. Proof-of-local-first checklist (rehearse once, then show judges)

Terminal layout: T1 GPU, T2 `openshell term`, T3 packet capture, T4 commands.

```bash
# T1: GPU is doing the work
nvidia-smi --query-gpu=name,utilization.gpu,temperature.gpu --format=csv -l 1
#     (in T4 meanwhile) nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv   -> the ollama runner
#     ollama ps   -> models loaded, PROCESSOR 100% GPU
# T2: live sandbox network activity and denials
openshell term
# T3: any NEW outbound connection from the host on the uplink (SSH excluded)
UPLINK=$(ip route get 1.1.1.1 | awk '{for(i=1;i<NF;i++) if ($i=="dev") {print $(i+1); exit}}'); echo "uplink: $UPLINK"
sudo tcpdump -ni "$UPLINK" -Q out '(tcp[tcpflags] & (tcp-syn|tcp-ack) == tcp-syn and not port 22) or (udp and not port 5353 and not port 67 and not port 68 and not port 123) or (ip6 and tcp and not port 22)'
```

`ip route get` only does a route lookup and sends nothing. `-Q out` and the `tcp[tcpflags]` syntax are standard tcpdump/pcap-filter on Linux.

Checklist (T4):

1. `grep -E '^(LLM_|INTERNAL_LLM_)' .env` and run the loopback guard from 3.2: every URL is `127.0.0.1`.
2. `env | grep -i -E '(openai|anthropic|openrouter|gemini|nvidia_inference)[a-z_]*key'` prints nothing.
3. `nemoclaw "$SB" inference get`: `ollama-local` + `nemotron-3-nano:30b`. `nemoclaw "$SB" status` shows Inference healthy.
4. `sudo ss -ltnp | grep -E ':(8787|8788|8790|8791|8792|11434|11435|18789|28787|28791)\b'`: app, Ollama and dashboard on `127.0.0.1`; Caddy on `$BRIDGE_IP` only; `0.0.0.0:11435` is NemoClaw's token-gated Ollama proxy (by design).
5. Run `make demo` (prints `mode: llm`) and the 6.6 agent prompt. Meanwhile T1 shows GPU utilisation and T3 shows **no** new outbound connections. If T3 prints a line, find the process with `sudo ss -tunp`. System noise (DNS, NTP) is possible; explain it, don't hide it.
6. `sudo journalctl -u ollama --since "10 min ago" | grep -E 'POST +"/v1/chat/completions"' | tail` shows the model requests, from local addresses only (if Ollama runs as the systemd service).
7. In T2, show the blocked `api.openai.com` request from section 7 and the allowed `/mcp` calls.
8. Strongest proof, if you are at the physical console (it drops SSH): unplug Ethernet / turn off Wi-Fi (`nmcli networking off`), re-run `DEMO_MODE= make demo` and one agent turn, then `nmcli networking on`.

Optional: the DGX Dashboard at `http://localhost:11000` shows memory and GPU (source: [NVIDIA dev forum DGX Spark FAQ](https://forums.developer.nvidia.com/t/dgx-spark-gb10-faq/347344). Forum, not official docs).

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `421 Invalid Host header` from an MCP URL | Request reached the Python server without the Host rewrite: you hit the server directly, or Caddy is not the one listening. Check `ss -ltnp` and the Caddyfile `header_up Host`. |
| `401` from intake MCP | Missing or wrong invitation token. Tokens are per client: make a new one (6.3), then `openclaw mcp set aceops-intake ...` again and `gateway restart`. |
| `policy_denied` / CONNECT 403 in sandbox | Preset not applied or binary path differs: `openshell term` shows the binary; add it to `aceops-mcp-bridge.yaml`; re-run `policy add --from-file`. |
| `upstream_unreachable` | Caddy not bound on the IP `host.openshell.internal` resolves to, or ufw blocks the subnet (6.2). |
| `caddy run` fails "cannot assign requested address" | `BRIDGE_IP` is not a host interface: use the `openshell-docker` gateway IP (6.1). |
| `make demo`: "LLM_BASE_URL is unreachable" | Ollama down or wrong port: `systemctl status ollama`, `curl -s 127.0.0.1:11434/v1/models`. The client deliberately does not fall back to scripted mode. |
| Client answers mostly `N/A` | The model is not returning bare JSON in 200 tokens: run 3.3; use `llama3.1:8b`; re-warm with `keep_alive` (2A). |
| `port 8787 is already in use` | `make demo-stop` (stops intake, board, live loop). SDLC and Caddy have their own PID files: `kill "$(cat data/sdlc.pid)" "$(cat data/caddy.pid)"`. |
| Bridge or SDLC dead after re-running `make demo` | You put their PIDs in `data/demo.pids`; `make demo` kills those first. Restart them (sections 4 and 6.2) with their own PID files. |
| NemoClaw onboarding: tool-call validation fails | Ollama < 0.32.9 or model template issue: upgrade Ollama, or use `qwen3.6:35b`; `nemoclaw onboard --resume`. |
| Onboarding interrupted | `nemoclaw onboard --resume`; start over with `nemoclaw onboard --fresh` ([quickstart](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/get-started/quickstart)). |
| Dashboard URL dead | `nemoclaw "$SB" recover`, then `nemoclaw "$SB" dashboard-url --quiet` ([Spark playbook](https://build.nvidia.com/spark/nemoclaw/instructions)). |
| Agent turns time out on the local model | Re-onboard with `NEMOCLAW_AGENT_TIMEOUT=300` (onboarding-time setting, [commands reference](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/commands)); keep models warm. |
| Host feels frozen / `NV_ERR_NO_MEMORY` | Too much in unified memory: `ollama stop <model>`; never run managed vLLM next to big Ollama models ([vLLM page warning](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/inference/local-inference/set-up-vllm)). |
| `nemoclaw "$SB" rebuild` refuses (credential-bearing content) | `nemoclaw "$SB" exec -- openclaw mcp unset aceops-intake`, rebuild, then re-add (6.5). |
| Docker permission denied | `sudo usermod -aG docker $USER && newgrp docker`. |
| Logs | `nemoclaw "$SB" logs --follow`, `data/logs/*.log`, `journalctl -u ollama -f`, `openshell term`. |

---

## 10. What to declare in the submission (only what you actually ran)

Collect the facts:

```bash
nemoclaw --version; openshell --version; nemoclaw "$SB" status | grep -i -E 'agent|inference|model'
ollama --version; ollama list; nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
cat /etc/dgx-release 2>/dev/null | head -3; nemoclaw "$SB" policy list
```

Template (delete any line you did not do):

> **Runtime:** NemoClaw `<version>` (OpenShell `<version>`, OpenClaw `<version>`) on a Dell Pro Max with GB10 (DGX OS `<version>`). OpenClaw runs in the OpenShell sandbox `aceops`, network policy tier Restricted, plus one custom preset (`aceops-mcp-bridge`) that allows only `http://host.openshell.internal:28787/mcp` and `:28791/mcp`. Baseline cloud entries (`nvidia`, `clawhub`, `openclaw_api`, `openclaw_docs`, `npm_registry`) were excluded.
> **Inference:** all local. Ollama `<version>` on `127.0.0.1:11434` serving `nemotron-3-nano:30b` (OpenClaw agent, tool calling) and `llama3.1:8b` (client/internal agents), 100% on the GB10 GPU. No hosted provider configured; no API keys present.
> **Our services:** ACE Ops intake MCP and SDLC MCP (official `mcp` Python SDK, Streamable HTTP), admin APIs and board, all on `127.0.0.1`. The sandbox reaches the two MCP endpoints through a Caddy reverse proxy bound to the OpenShell bridge IP. The SDLC MCP exposes no approval tools, and the approval API is unreachable from the sandbox.
> **Proof shown:** `nvidia-smi`/`ollama ps` during runs, `openshell term` denials, host `tcpdump` with no new outbound connections, [offline run].

Do **not** claim: NemoClaw-managed MCP (`nemoclaw mcp add`) unless you completed Appendix B; NIM/vLLM unless you served with them; Telegram/Slack unless set up; "fully air-gapped" unless you did step 8.8.

---

## Appendix A. OpenClaw as the client's AI, feeding the live board

`make demo` always runs the Python client agent. To let OpenClaw answer the checklist instead, start the services by hand (the same steps as `scripts/run_demo.sh`, minus the client agent):

```bash
cd "$REPO" && make demo-stop
mkdir -p data/logs data/out
rm -f data/out/brd.md data/out/work_items.json data/out/progress.json data/out/client.json data/out/overrides.json
export PYTHONPATH="$PWD/src" PYTHONUNBUFFERED=1
: > data/demo.pids
nohup .venv/bin/python -m intake.main > data/logs/intake.log 2>&1 & echo $! >> data/demo.pids
nohup .venv/bin/python -m board       > data/logs/board.log  2>&1 & echo $! >> data/demo.pids
until curl -fsS -m 2 -o /dev/null http://127.0.0.1:8788/openapi.json; do sleep 0.5; done
ADMIN_TOKEN=$(grep '^ADMIN_TOKEN=' .env | cut -d= -f2-)
curl -fsS -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  http://127.0.0.1:8788/admin/clients > data/.openclaw-client.json && chmod 600 data/.openclaw-client.json
python3 -c 'import json; d=json.load(open("data/.openclaw-client.json")); open("data/out/client.json","w").write(json.dumps({"id": d["id"]})+"\n")'
INTAKE_TOKEN=$(python3 -c 'import json;print(json.load(open("data/.openclaw-client.json"))["invitation_token"])')
nohup .venv/bin/python -m internal.run --live > data/logs/internal.log 2>&1 & echo $! >> data/demo.pids
sleep 3; grep '^mode:' data/logs/internal.log      # expect: mode: live
```

`internal.run --live` follows the client in `data/out/client.json` (`ensure_client` in `src/internal/run.py`). Stop these three with `make demo-stop`. Then re-run 6.5 (`openclaw mcp set aceops-intake ...` with this `$INTAKE_TOKEN`) and `nemoclaw "$SB" gateway restart`, plus the SDLC and Caddy starts from sections 4 and 6.2. Drive it from `openclaw tui` (6.6). The board at :8790 updates as answers land.

## Appendix B. NemoClaw-managed MCP (`nemoclaw mcp add`), optional, not run end-to-end

NVIDIA calls this "the intended configuration": the bearer stays in OpenShell, the policy is MCP-aware (`protocol: mcp`, method rules, `--deny-tool`), and nothing secret sits in `openclaw.json` ([about managed MCP](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/manage-sandboxes/mcp-servers/about-managed-mcp-servers)). Requirements, quoted from [Add an MCP Server](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/manage-sandboxes/mcp-servers/add-an-mcp-server):
HTTPS only; no `127.0.0.1`/`host.openshell.internal`/`host.docker.internal`; a private IPv4 literal is allowed with `--trusted-private-host`, but the certificate needs a matching IP SAN; a private CA goes in `NEMOCLAW_CORPORATE_CA_BUNDLE` and then a sandbox rebuild; exactly one `--env` bearer per server; a firewall limiting the listener to the gateway subnet.

Outline (budget 30+ minutes including the rebuild):

1. HTTPS reverse proxy on `$BRIDGE_IP` (for example `:28443` → `127.0.0.1:8787`, `:28444` → `127.0.0.1:8791`) with the same `Host` rewrite, using a cert for IP `$BRIDGE_IP` from a private CA. Caddy's `tls internal` keeps its CA under its data dir `pki/authorities/local` ([Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)). **Unverified:** the exact root file name, and Caddy's cert choice for SNI-less IP connections. A cert made with `openssl` is the safer bet.
2. `unset` the agent-native intake entry first: `nemoclaw "$SB" exec -- openclaw mcp unset aceops-intake`.
3. `export NEMOCLAW_CORPORATE_CA_BUNDLE=/path/to/root-ca.pem && nemoclaw "$SB" rebuild --yes` ([corporate CA trust](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/security/configure-corporate-ca-trust)).
4. Register (the SDLC server ignores bearer tokens, but NemoClaw requires one, so use any dedicated value):
   ```bash
   read -rsp 'intake invitation token: ' ACEOPS_INTAKE_MCP_TOKEN; echo; export ACEOPS_INTAKE_MCP_TOKEN
   nemoclaw "$SB" mcp add aceops-intake --url "https://$BRIDGE_IP:28443/mcp" --env ACEOPS_INTAKE_MCP_TOKEN --trusted-private-host "$BRIDGE_IP"
   unset ACEOPS_INTAKE_MCP_TOKEN
   export ACEOPS_SDLC_MCP_TOKEN=$(openssl rand -hex 16)
   nemoclaw "$SB" mcp add aceops-sdlc --url "https://$BRIDGE_IP:28444/mcp" --env ACEOPS_SDLC_MCP_TOKEN --trusted-private-host "$BRIDGE_IP"
   unset ACEOPS_SDLC_MCP_TOKEN
   nemoclaw "$SB" mcp status aceops-intake --json     # trustedPrivateTarget.state must be "match"
   ```
   With managed MCP, in-sandbox `curl` is denied by design; use `mcp status`, not curl ([commands reference](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/reference/commands)).

## Appendix C. Fallback: OpenClaw on the host (no sandbox)

Use this only if section 6 is blocked late. It still satisfies "uses OpenClaw", but it has **no OpenShell isolation**, so declare it honestly.

```bash
nemoclaw "$SB" stop                                   # frees dashboard port 18789; this also unloads Ollama models (re-warm, 2A)
ollama launch openclaw --model nemotron-3-nano:30b    # installs OpenClaw via npm, starts gateway + TUI
openclaw configure --section web                      # turn web search OFF (Ollama's bundled web search is a cloud service)
openclaw mcp set aceops-sdlc '{"url":"http://127.0.0.1:8791/mcp","transport":"streamable-http"}'
openclaw mcp doctor aceops-sdlc --probe
```

Source: [Ollama OpenClaw integration](https://docs.ollama.com/integrations/openclaw). OpenClaw needs a context window of 64k or more for local models (same page). No Caddy is needed: Host is already `127.0.0.1`.

## Appendix D. Optional chat channel (Telegram), needs internet

Only if everything else is done. It needs a bot token from @BotFather, internet access to Telegram for the channel itself (not an LLM call), a sandbox rebuild (unset `aceops-intake` first, see 6.5), and it widens egress with the `telegram` preset, which weakens the section 7 story.

```bash
export TELEGRAM_BOT_TOKEN="<from @BotFather>" TELEGRAM_ALLOWED_IDS="<your telegram user id>"
nemoclaw "$SB" channels add telegram      # applies the telegram preset, offers the rebuild
```

Source: [Set Up Telegram](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/manage-sandboxes/messaging-channels/set-up-telegram), [Add Channels After Onboarding](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/manage-sandboxes/messaging-channels/add-channels-after-onboarding). Then ask OpenClaw to post "New ticket for Data Analyst: ..." from `list_tickets` output.

## Appendix E. Files in `src/sdlc/runtime/`

| File | Format verified against |
|---|---|
| `Caddyfile.mcp-bridge` | Caddy docs (concepts, global options, `reverse_proxy`). Run `caddy validate` on the box. |
| `aceops-mcp-bridge.yaml` | NemoClaw custom-preset docs + `schemas/policy-preset.schema.json` at v0.0.137 (0 errors) |
| `openclaw-mcp-aceops-sdlc.json`, `openclaw-mcp-aceops-intake.json` | OpenClaw 2026.9.2 `docs/cli/mcp.md` (Streamable HTTP fields) |
| `gb10.env.example` | The repo's own dotenv parsers (`scripts/run_demo.sh`, `src/intake/config.py`, `src/sdlc/config.py`) |
