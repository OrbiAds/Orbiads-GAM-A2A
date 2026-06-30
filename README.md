# Orbiads-GAM-A2A — A2A agents for Google Ad Manager (via OrbiAds)

**Clone-and-deploy examples** proving the whole path, end to end: **build a Google Ad Manager agent,
connect it to OrbiAds (MCP), deploy it to Google's Agent Platform (Vertex Agent Engine), make it
A2A-discoverable, and compose multi-agent business cases — including the AdCP media-buy standard.**

> Companion repository for the **OrbiAds Academy "OrbiAds in A2A"** article series.
> MCP = agent ↔ tools. A2A (Agent2Agent) = agent ↔ agent.

## 👉 The tutorial
**[TUTORIAL.md](./TUTORIAL.md)** — complete, concrete, **generic** walkthrough (placeholders, no real IDs):
prerequisites → project/APIs → agent code → OAuth connection → Agent Engine deployment → Agent Card /
registry → A2A (orchestrator) → multi-agent business case → **native AdCP** → what's next → teardown.

`agent-card.json` = an A2A Agent Card template.

## The 4 agents (progression)
| Folder | Demonstrates | Part |
|---|---|---|
| `gam_sentinel/` | A single GAM A2A agent (instruction + filtered OrbiAds MCP), deployable to Agent Engine | 2–5 |
| `orchestrator/` | A2A: `registry_search_agents` → delegation to `gam_sentinel` | 6–7 |
| `gam_optimizer/` | Business case, **3 async agents**: forecast ∥ format/CTR → synthesis | 8 |
| `adcp_gateway/` | **Native AdCP**: buy agent → `create_media_buy` → `deals(adcp_validate)` then `deals(adcp_preview)` → GAM DealSpec, **read-only** | 8bis |

> Agent prompts are in **English**; every agent that touches data runs a **NETWORK CHECK** (prints the
> active network, stops if unexpected). The **model is a parameter** (`MODEL` in `.env`) — pick the one
> that fits your use; a large nested JSON (AdCP) may need a stronger model than `flash`.

## Quickstart (local)
```bash
git clone https://github.com/OrbiAds/Orbiads-GAM-A2A.git
cd Orbiads-GAM-A2A
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1) Configure each agent: copy .env.example -> .env in the agent folder
cp gam_sentinel/.env.example gam_sentinel/.env       # same for the others
# Fill MODEL + ORBIADS_MCP_TOKEN (token obtained via `python get_token.py`)

# 2) Launch the ADK dev UI (all 4 agents)
adk web .                                            # http://127.0.0.1:8000

# or serve the GAM agent over A2A:
uvicorn gam_sentinel.agent:a2a_app --port 10000      # /.well-known/agent.json
```

Get an OrbiAds token: `python get_token.py` (DCR + PKCE + consent) writes the token into `.env`.
See **Part 3** of the tutorial.

> ⚠️ Stay on a **test GAM network** (never a real client network). The active network is server-side
> state, switched via the MCP tool `network(action='switch_network', ...)`. Agents print the active
> network and stop if it's unexpected (NETWORK CHECK).

## Security
`.env` files (tokens), `.adk/` state and raw screenshots are **not** versioned (see `.gitignore`).
Only redacted screenshots (`captures/web/*.webp`) are published. **MIT** licensed.
