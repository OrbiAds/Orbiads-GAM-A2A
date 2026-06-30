# Complete tutorial — A GAM agent connected to OrbiAds, deployed and orchestrated over A2A

> **Generic** : replace the `UPPERCASE` placeholders. No real values hard-coded.
> Written "from scratch": every step, every pitfall encountered (⚠️), every official link.
>
> Placeholders : `PROJECT_ID`, `PROJECT_NUMBER`, `REGION` (e.g. `us-central1`), `NETWORK_CODE` (test GAM
> network), `CONNECTOR_NAME` (e.g. `orbiads`), `AGENT_ENGINE_ID`, `CLIENT_ID`/`CLIENT_SECRET`.

## 📖 Official documentation (keep it open)
- ADK (Agent Development Kit) : <https://adk.dev/> · tools tutorial <https://adk.dev/tutorials/multi-tool-agent/>
- ADK + MCP : <https://adk.dev/tools-custom/mcp-tools/> · ADK auth : <https://adk.dev/tools-custom/authentication/>
- ADK A2A : <https://google.github.io/adk-docs/a2a/> · A2A codelab : <https://codelabs.developers.google.com/codelabs/currency-agent>
- Agent Engine/Runtime deployment : <https://adk.dev/deploy/agent-runtime/>
- Agent Identity (managed auth) : <https://adk.dev/integrations/agent-identity/> ·
  overview <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity-overview>
- 3LO connectors : <https://docs.cloud.google.com/iam/docs/manage-auth-providers> ·
  <https://docs.cloud.google.com/iam/docs/auth-with-3lo>
- Agent Registry : <https://docs.cloud.google.com/agent-registry/register-agents> ·
  register an A2A agent <https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-a2a-agent>
- Vertex models : <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models>
- A2A protocol : <https://a2a-protocol.org/latest/specification/> · OAuth DCR : RFC 7591 / PKCE : RFC 7636

---

## Part 0 — Prerequisites and installation

- An **OrbiAds** account connected to your GAM network. MCP endpoint : `https://orbiads.com/mcp`.
- `gcloud` installed + **up to date** :
  ```bash
  gcloud auth login
  gcloud components update        # ⚠️ required: the "agent-identity connectors" commands are recent
  gcloud components install alpha # ⚠️ otherwise "Invalid choice: agent-identity"
  ```
- Python 3.11+ and a dedicated venv :
  ```bash
  python -m venv .venv && .venv/Scripts/activate           # Windows; otherwise: source .venv/bin/activate
  pip install "google-adk[a2a,agent-identity]==2.3.0" "mcp==1.28.1" \
              "google-cloud-aiplatform[agent_engines]" "google-cloud-secret-manager" \
              uvicorn httpx python-dotenv
  pip install "opentelemetry-api==1.42.1" "opentelemetry-sdk==1.42.1"
  ```
  > ⚠️ **Pitfall encountered** : `google-cloud-aiplatform[agent_engines]` pulls in `opentelemetry 1.43`, which **breaks**
  > ADK 2.3.0 (which wants `<=1.42.1`). Hence the `==1.42.1` repin last. Without it: conflict at deployment time.
  > ⚠️ `google-adk` **alone** is not enough: you need the `[a2a,agent-identity]` extra **and** `mcp`.

---

## Part 1 — GCP project, billing, APIs

```bash
gcloud projects create PROJECT_ID --name="Agent A2A"
gcloud billing projects link PROJECT_ID --billing-account=YOUR_BILLING_ID
gcloud config set project PROJECT_ID
gcloud auth application-default set-quota-project PROJECT_ID

gcloud services enable \
  aiplatform.googleapis.com iamconnectors.googleapis.com secretmanager.googleapis.com \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com storage.googleapis.com
```
> ⚠️ **Pitfall encountered** : `billing projects link` → `Cloud billing quota exceeded` means your billing account
> has reached its quota for the **number of projects**. Fix: use another billing account, or reuse an
> existing project that is already billed.
> ⚠️ `aiplatform` = Vertex (the model) **and** Agent Engine. `iamconnectors` = the OAuth connector. Enable them
> before Part 3, otherwise `SERVICE_DISABLED` (and allow ~1-2 min of propagation after enabling).

---

## Part 2 — The GAM agent code

Directory layout (each subfolder = one agent for ADK) :
```
mon-agent/
  gam_sentinel/
    __init__.py
    agent.py
    .env
    requirements.txt
```

`gam_sentinel/__init__.py` :
```python
from . import agent      # ADK discovers root_agent here
```

`gam_sentinel/agent.py` :
```python
import os
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.a2a.utils.agent_to_a2a import to_a2a

load_dotenv()
MCP_URL = os.environ.get("ORBIADS_MCP_URL", "https://orbiads.com/mcp")
TOKEN   = os.environ.get("ORBIADS_MCP_TOKEN", "")
MODEL   = os.environ.get("MODEL", "gemini-2.5-flash")
PORT    = int(os.environ.get("A2A_PORT", "10000"))

orbiads = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=MCP_URL,
        headers={"Authorization": f"Bearer {TOKEN}"} if TOKEN else {},
    ),
    # "scope the skills": 2-3 tools, not 50 (precision + lean context)
    tool_filter=["check_credentials", "select_gam_network", "inventory"],
)

root_agent = LlmAgent(
    name="gam_inventory_sentinel",
    model=MODEL,
    instruction=(
        "Tu es une sentinelle d'inventaire GAM en LECTURE SEULE. "
        "1) check_credentials (confirm connection + network). 2) inspect the inventory (ad units). "
        "3) flag low-availability or non-compliant units. You NEVER write."
    ),
    tools=[orbiads],
)

# Expose the agent over A2A: serves /.well-known/agent.json + receives tasks
a2a_app = to_a2a(root_agent, port=PORT)
```

`gam_sentinel/requirements.txt` :
```
google-adk[a2a,agent-identity]==2.3.0
mcp==1.28.1
google-cloud-aiplatform[agent_engines]
google-cloud-secret-manager
```

`gam_sentinel/.env` (config; auth = Part 3) :
```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=PROJECT_ID
GOOGLE_CLOUD_LOCATION=REGION
MODEL=gemini-2.5-flash
ORBIADS_MCP_URL=https://orbiads.com/mcp
A2A_PORT=10000
```
> ⚠️ **Major pitfall** : ADK loads the `.env` **of the agent folder** (`gam_sentinel/.env`), **not** your
> shell environment variables. It is THIS file that sets the model AND the auth. Symptom if the auth in it is
> wrong: the MCP returns `401`, the tools don't load, and the model **"narrates" the tool call**
> (`Unexpected tool call: print(default_api.check_credentials())`) instead of executing it.
> ⚠️ **Model** : check that `MODEL` is available via Vertex in your `PROJECT_ID`/`REGION`
> (<https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models>). Otherwise `Publisher model ... not
> found`. (`gemini-2.5-flash` is widely available.)

---

## Part 3 — Retrieve AND inject your OrbiAds connection token (in detail)

OrbiAds is a **standard OAuth server** (cf RFC 7591 DCR + PKCE RFC 7636). Discovery :
`GET https://orbiads.com/mcp/.well-known/oauth-authorization-server` → exposes :
- `authorization_endpoint` = `https://orbiads.com/mcp/authorize`
- `token_endpoint` = `https://orbiads.com/mcp/token`
- `registration_endpoint` = `https://orbiads.com/mcp/register` (DCR)
- `grant_types` = `authorization_code`, `refresh_token` · PKCE = `S256` · (no `client_credentials`).

There are **two tokens** : an **access token** (≈ 1 h, used as the `Authorization: Bearer` header) and a
**refresh token** (long-lived, used to reissue access tokens). **⚠️ The refresh token ROTATES** on
each use: the old one is invalidated, `/token` returns a new refresh — you must re-save it.

### 3.1 — Retrieve the tokens (full OAuth flow)
> 💡 **The simplest way (self-service, no CLI)** : OrbiAds → **Settings → Agents → "Connect an agent"**
> provisions an OAuth client (client_id + secret) in one click — see Part 5bis. The `get_token.py` script
> below is the **CLI equivalent** (useful to obtain a test *bearer* directly).

The `get_token.py` script (provided in the lab) does, in order :
1. **DCR** — registers an OAuth client : `POST /mcp/register` with a local `redirect_uri`
   (`http://localhost:8765/callback`) → returns a `client_id`.
2. **PKCE** — generates a `code_verifier` + `code_challenge` (S256).
3. **Consent** — opens `…/mcp/authorize?...` in your browser; you sign in with your Google
   account and approve (this is the "3-legged" flow: on behalf of the user).
4. **Callback** — a tiny local server captures the redirected `code`.
5. **Exchange** — `POST /mcp/token` (`grant_type=authorization_code` + `code_verifier`) → **access_token**
   + **refresh_token**.

```bash
python get_token.py        # ouvre le navigateur ; à la fin, écrit dans .env :
#   ORBIADS_MCP_CLIENT_ID, ORBIADS_MCP_TOKEN (access), ORBIADS_MCP_REFRESH_TOKEN
```
> Heart of the script (to understand) :
> ```python
> # 1) DCR
> reg = POST("/mcp/register", {"client_name":"...", "redirect_uris":[REDIRECT],
>            "grant_types":["authorization_code","refresh_token"], "token_endpoint_auth_method":"none"})
> client_id = reg["client_id"]
> # 2) PKCE
> verifier  = secrets.token_urlsafe(64)
> challenge = b64url(sha256(verifier))
> # 3) ouvrir /mcp/authorize?response_type=code&client_id=...&redirect_uri=...&scope=openid ...
> #    &code_challenge=challenge&code_challenge_method=S256
> # 4) capter ?code=... sur http://localhost:8765/callback
> # 5) échange
> tok = POST_form("/mcp/token", {"grant_type":"authorization_code","code":code,
>                 "redirect_uri":REDIRECT,"client_id":client_id,"code_verifier":verifier})
> access, refresh = tok["access_token"], tok["refresh_token"]
> ```

### 3.2 — Inject the token into the agent
ADK reads the agent's `.env`. **So the token goes into `gam_sentinel/.env`** :
```
ORBIADS_MCP_CLIENT_ID=CLIENT_ID
ORBIADS_MCP_TOKEN=COLLE_L_ACCESS_TOKEN
ORBIADS_MCP_REFRESH_TOKEN=COLLE_LE_REFRESH_TOKEN
```
The code (`agent.py`, Part 2) reads `ORBIADS_MCP_TOKEN` and puts it in `Authorization: Bearer ...`.
> ⚠️ Put it in the **right** `.env` (the one in the agent folder you launch). A `.env` in connector mode or with
> an expired token → `401` → tools not loaded (cf Part 2).

### 3.3 — Handle expiry (reissue an access token)
The access token expires (~1 h). To reissue it **without a browser**, via the refresh token :
```bash
curl -s -X POST https://orbiads.com/mcp/token \
  -d "grant_type=refresh_token" -d "refresh_token=YOUR_REFRESH" -d "client_id=YOUR_CLIENT_ID"
# → nouveau access_token (+ un nouveau refresh_token : REMPLACE l'ancien dans ton .env !)
```
> ⚠️ **Pitfall encountered** : if you re-mint but don't **save** the new refresh token, the next one
> fails (`invalid_grant: refresh token does not exist`). Always rewrite the rotated refresh.

### 3.4 — For a MANAGED agent (Agent Engine) : stop managing tokens entirely
See **Part 5bis** (Agent Identity Auth Manager) : Google handles consent + vault + rotation +
injection. Your agent then has **no** token and no auth code at all.

---

## Part 4 — Run and verify locally (canonical runner)

> ⚠️ **Pitfall encountered** : do **not** test by sending raw JSON-RPC to the A2A endpoint — it short-circuits the
> runner's tool-execution loop. Use `adk run` / `adk web` (cf <https://adk.dev/tutorials/multi-tool-agent/>).

```bash
adk run gam_sentinel          # REPL; ask a question, the agent calls check_credentials + inventory
# or the dev UI (recommended for screenshots):
adk web .                      # -> http://127.0.0.1:8000
```
> ⚠️ **Data safety** : before any request, make sure you are on a **test GAM network** (never a real
> client network). The active network is an OrbiAds **server state**. To change it, call the **MCP
> tool** `network` (via your MCP client — Claude Desktop, or a small `mcp` script with your bearer) :
> `network(action="switch_network", params={"network_code": "NETWORK_CODE"})`. This is NOT a shell command
> nor an `adk` subcommand.

---

## Part 5 — Deploy into the Agent Platform (Agent Engine)

Ref : <https://adk.dev/deploy/agent-runtime/>
> ⚠️ **Auth of the deployed agent** : a managed agent cannot perform the browser consent. For it to
> authenticate, set up **Part 5bis (Agent Identity connector) BEFORE/with this deployment** and
> reference it in `agent.py` (`auth_scheme`). An agent deployed without this auth will connect to OrbiAds
> but won't be able to retrieve a credential ("Failed to retrieve credential").
```bash
python -m google.adk.cli deploy agent_engine \
  --project=PROJECT_ID --region=REGION --display_name="GAM Inventory Sentinel" gam_sentinel
# → renvoie AGENT_ENGINE_ID + URL playground
```
> ⚠️ **Pitfalls encountered** : `No module named 'vertexai'` → install `google-cloud-aiplatform[agent_engines]` ;
> opentelemetry conflict → repin `==1.42.1` (Part 0). To update the same agent (no duplicate) :
> add `--agent_engine_id=AGENT_ENGINE_ID`.

Verify : console **Vertex AI → Agents → Agent Engines**.

## Part 5bis — Clean managed auth : the Agent Identity connector (3LO)

Ref : <https://adk.dev/integrations/agent-identity/> · <https://docs.cloud.google.com/iam/docs/auth-with-3lo>

1. **Get a confidential client from OrbiAds.** The `redirect_uri` MUST be the **connector callback** :
   `https://iamconnectorcredentials.googleapis.com/v1/projects/PROJECT_ID/locations/REGION/connectors/CONNECTOR_NAME/oauthcallback`

   **Recommended path (self-service, no CLI)** : OrbiAds → **Settings → Agents → "Connect an agent"** →
   *Name* + paste this **Redirect URI** (the field already shows the template) → **Create** → copy the **`CLIENT_ID`**
   + the **`CLIENT_SECRET`** (shown only once). *(Validated live: a client created this way does create an
   ENABLED connector and connects to OrbiAds → GAM.)*

   **Alternative CLI path (DCR)** :
   ```bash
   CB="https://iamconnectorcredentials.googleapis.com/v1/projects/PROJECT_ID/locations/REGION/connectors/CONNECTOR_NAME/oauthcallback"
   curl -s -X POST https://orbiads.com/mcp/register -H "Content-Type: application/json" -d "{
     \"client_name\":\"agent-identity\",\"redirect_uris\":[\"$CB\"],
     \"grant_types\":[\"authorization_code\",\"refresh_token\"],\"response_types\":[\"code\"],
     \"token_endpoint_auth_method\":\"client_secret_post\"}"
   # → CLIENT_ID + CLIENT_SECRET
   ```
   > ⚠️ The client's `redirect_uri` **must** match the connector callback, otherwise consent
   > fails at runtime (redirect mismatch). So create the client WITH this callback (not a localhost).
2. **Create the connector** :
   ```bash
   gcloud alpha agent-identity connectors create CONNECTOR_NAME --project=PROJECT_ID --location=REGION \
     --three-legged-oauth-authorization-url="https://orbiads.com/mcp/authorize" \
     --three-legged-oauth-token-url="https://orbiads.com/mcp/token" \
     --three-legged-oauth-client-id="CLIENT_ID" --three-legged-oauth-client-secret="CLIENT_SECRET" \
     --allowed-scopes="openid,https://www.googleapis.com/auth/userinfo.email"
   ```
3. **Reference it in the agent** (instead of the bearer) :
   ```python
   from google.adk.integrations.agent_identity import GcpAuthProvider, GcpAuthProviderScheme
   from google.adk.auth.credential_manager import CredentialManager
   scheme = GcpAuthProviderScheme(
       name="projects/PROJECT_ID/locations/REGION/connectors/CONNECTOR_NAME",
       scopes=["openid","https://www.googleapis.com/auth/userinfo.email"])
   CredentialManager.register_auth_provider(GcpAuthProvider())   # ⚠️ classmethod (PAS AuthProviderRegistry())
   orbiads = MCPToolset(connection_params=StreamableHTTPConnectionParams(url="https://orbiads.com/mcp"),
                        tool_filter=["check_credentials","inventory"], auth_scheme=scheme)
   ```
> ⚠️ **Pitfalls encountered** : (a) `agent-identity connectors` missing → `gcloud components update`. (b) The
> `iamconnectors` API must be enabled (+ propagation). (c) At runtime : `No auth provider registered for ...
> gcpAuthProviderScheme` if you do `AuthProviderRegistry().register(...)` (empty registry) instead of the
> **classmethod** `CredentialManager.register_auth_provider(...)`. (d) Consent remains **human, once**;
> the Agent Engine playground does NOT orchestrate it (it calls with a technical identity) → the
> consent happens in Agentspace/Gemini Enterprise. The `client_secret` is required by the connector
> but **not verified by OrbiAds** (security = PKCE + redirect_uri).

---

## Part 6 — The Agent Card in the Agent Registry (discoverability)

Ref : <https://docs.cloud.google.com/agent-registry/register-agents> ·
<https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-a2a-agent>

> ⚠️ **Pitfall encountered** : `adk deploy agent_engine` on its own registers the agent as **`CUSTOM`** (API query), **without
> an Agent Card** (`has card: False`) → not callable over A2A. You need an **Agent Card** (`/.well-known/agent.json`).

- **Auto** : deploy/serve an agent that exposes the Agent Card → the registry scans and indexes it.
- **Console** : Gemini Enterprise → your app → **Agents → Add → Custom agent via A2A** → paste the Agent Card
  JSON (template : [agent-card.json](./agent-card.json), `url` = A2A endpoint) + the connector's OAuth.

Serve the agent over A2A locally (the card is already built by `to_a2a`, Part 2) :
```bash
uvicorn gam_sentinel.agent:a2a_app --port 10000     # carte : http://127.0.0.1:10000/.well-known/agent.json
```
> ⚠️ **Pitfall encountered** : the card contains its own `url` (with a port). Serve the agent **on the same port**
> as the one listed in the card, otherwise the A2A caller → `503: All connection attempts failed`.

---

## Part 7 — A2A : an orchestrator that DISCOVERS then DELEGATES

`orchestrator/agent.py` :
```python
import os
from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.tools import FunctionTool
from google.adk.integrations.agent_registry import AgentRegistry

reg = AgentRegistry(project_id=os.environ["GOOGLE_CLOUD_PROJECT"],
                    location=os.environ["GOOGLE_CLOUD_LOCATION"])

def registry_search_agents(need: str) -> list[dict]:
    """Cherche les agents A2A disponibles dans l'Agent Registry."""
    res = reg.list_agents()
    return [{"name": a.get("displayName"), "id": a.get("name")} for a in res.get("agents", [])]

gam_remote = RemoteA2aAgent(
    name="gam_inventory_sentinel",
    description="GAM agent (inventory, read-only) reached over A2A.",
    agent_card=os.environ.get("GAM_A2A_CARD_URL", "http://127.0.0.1:10000/.well-known/agent.json"),
)

root_agent = LlmAgent(
    name="orchestrator", model=os.environ.get("MODEL", "gemini-2.5-flash"),
    instruction=("For any GAM request: 1) registry_search_agents to find the specialized agent, "
                 "2) delegate to the gam_inventory_sentinel sub-agent, 3) return its answer."),
    tools=[FunctionTool(registry_search_agents)],
    sub_agents=[gam_remote],
)
```
`orchestrator/.env` : same `GOOGLE_*` + `MODEL` + `GAM_A2A_CARD_URL=http://127.0.0.1:10000/.well-known/agent.json`.
Launch `gam_sentinel` (Part 6) **then** `adk web .` → `orchestrator` app : trace
`registry_search_agents` → `transfer_to_agent` → response from the GAM agent.

---

## Part 8 — Business case : a multi-agent optimization plan (async)

`gam_optimizer/agent.py` — 2 specialists **in parallel** + synthesis :
```python
import os
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

TOKEN=os.environ.get("ORBIADS_MCP_TOKEN",""); MODEL=os.environ.get("MODEL","gemini-2.5-flash")
def mcp(f): return MCPToolset(connection_params=StreamableHTTPConnectionParams(
    url="https://orbiads.com/mcp", headers={"Authorization":f"Bearer {TOKEN}"} if TOKEN else {}), tool_filter=f)

forecast_agent = LlmAgent(name="forecast_agent", model=MODEL, output_key="forecast_result",
  instruction="Estimate delivery POTENTIAL (read-only). check_credentials then reporting "
              "(get_traffic_data / get_standalone_forecast). Give a volume + 1 sentence.",
  tools=[mcp(["check_credentials","reporting","inventory"])])
format_agent = LlmAgent(name="format_agent", model=MODEL, output_key="format_result",
  instruction="Recommend FORMATS for CTR (read-only). check_credentials then "
              "reporting.run_custom_report (CTR by size, LAST_30_DAYS) + inventory (obsolete sizes). "
              "Give top formats + sizes to retire.",
  tools=[mcp(["check_credentials","reporting","inventory","formats"])])

specialists = ParallelAgent(name="specialists", sub_agents=[forecast_agent, format_agent])
synthesis = LlmAgent(name="synthesis_agent", model=MODEL,
  instruction=("Optimization plan from:\n— Potential: {forecast_result?}\n"
               "— Formats: {format_result?}\nGive: potential · formats to prioritize · sizes to retire."))
root_agent = SequentialAgent(name="gam_optimizer", sub_agents=[specialists, synthesis])
```
> ⚠️ **Pitfall encountered** : instruction templating `{var}` is **strict** → `KeyError` if a sub-agent's key
> is not yet in state. Use `{var?}` (optional) for `forecast_result`/`format_result`.

> ⚠️ **Prompt pitfall — the agent invents tools / numbers.** With a vague instruction ("via
> inventory, spot the obsolete sizes"), the LLM **hallucinates** a tool name (`listing_obsolete_ad_unit_sizes`),
> feeds itself the response as a parameter, then contradicts itself; or it outputs **placeholders** (`[CTR_DATA_HERE]`)
> and an **invented round number** (5,000,000). Fixes in the prompt : (a) **name the exact action**
> (`inventory` action `list_ad_unit_sizes`, **with no** parameter) ; (b) state that the **obsolescence judgement
> is the agent's job** (compare `fullDisplayString` against a known list), never a tool parameter ;
> (c) treat `width=0`/empty `fullDisplayString` as **responsive/fluid**, not "obsolete" ; (d) **forbid
> placeholders** `[…]` and invented numbers — either the tool's real value, or its absence stated plainly.

> ⚠️ **GAM Reporting pitfall** : the `AD_REQUEST_SIZES` dimension is **incompatible** with the
> `IMPRESSIONS`/`CLICKS` metrics in the default historical report (rejected by GAM). And `run_custom_report`
> **refuses `dateRange`** placed as-is in `params` (validation error). Concrete consequence : on a
> **test network with no traffic**, the `format_agent` cannot compute a CTR — it must **say so**, not
> make one up. This is the expected behavior after fixing the prompt.

`adk web .` → `gam_optimizer` app : parallel graph (forecast ∥ format) → `synthesis_agent`.

> 🔒 **English prompts + network guardrail.** The agents' instructions are in **English** (international
> reach) and every agent that touches data performs a **NETWORK CHECK** : it reads `networkCode` /
> `networkDisplayName` via `check_credentials`, displays them, and **stops if `autoBound=true` or if the
> network is not the expected one** — so it never reads a production network by mistake.

---

## Part 8bis — Native AdCP (an agent that speaks the buying standard)

OrbiAds already exposes an **AdCP** surface (Ad Context Protocol) — **don't invent a JSON brief**, use
the native tools. Note : they go through **parent tools** (parent>action pattern), not standalone
names :

| Capability | Actual MCP call | Type |
|---|---|---|
| Sell-side discovery (AdCP-formatted products) | `products` → discovery action `get_products_adcp` | read-only |
| Validate a `create_media_buy` against schema v3 | `deals(action='adcp_validate', params={request})` | read-only |
| Translate an AdCP request into a `DealSpec` (without executing) | `deals(action='adcp_preview', params={request})` | read-only |
| Execute end to end | `deals(action='adcp_create', params={request, confirmation_token})` | **write** |

**The A2A case** (folder `adcp_gateway/`) : a **buyer agent** sends an AdCP `create_media_buy` request
→ the OrbiAds agent **validates** it (`adcp_validate`) then **previews** it as a GAM deal (`adcp_preview`),
**100% read-only** (`adcp_create` forbidden by the prompt). Sample request :
`adcp_gateway/sample_adcp_request.json`. Screenshot : `captures/web/06-adcp-gateway-preview.webp`.

> ℹ️ **The model is a user choice — this tutorial validates the APPROACH, not a model.** Observed
> along the way : a large nested AdCP JSON can make gemini-2.5-**flash** "code" the call
> (`MALFORMED_FUNCTION_CALL` : `print(default_api.deals(...))`). For deeply nested arguments, a
> beefier model (e.g. gemini-2.5-pro) makes the run more reliable. Set the model that suits YOUR usage via
> `MODEL` in the `.env` — nothing in the code is tied to it.

> ⚠️ **Pitfall encountered** : `tool_filter` filters by **tool name**, not by action. Since the read-only
> AdCP actions live under the `deals` parent (which also has `adcp_create` as a write), you cannot isolate them
> at the tool level. We rely on (a) the prompt and (b) OrbiAds's **confirmation_token** (`adcp_create`
> refuses to run without a token issued by a preview). For a **hard** read-only, you would need a
> server-side read-only scope.

> ⚠️ **Pitfall encountered** : `adcp_preview` performs a **real GAM advertiser lookup**. Without a matching advertiser
> (`brand.domain`), it returns the **actionable** error `ADCP_ADVERTISER_UNRESOLVED` → provide
> `ext.orbiads_advertiser_company_id` (the GAM `Company` ID). This is the expected behavior, not a bug.

---

## Part 9 — Cleanup, logging & confidentiality (teardown)

> ⚠️ **Cloud logging PERSISTS.** An agent deployed on Agent Engine leaves two persistent traces
> **in the deployment GCP project** : (a) **Cloud Logging** (default retention **30 days**, bucket
> `_Default`, configurable 1–3650 d) ; (b) the **managed Agent Engine sessions** (`create_session` …) that
> keep the **conversation history until `delete_session`**. Everything the agent traces — including the
> **GAM data returned by the tools** — can appear there. For a real deployment (and consistent with
> OrbiAds's **zero-storage** principle) : reduce log retention, limit verbose tracing, and
> **purge sessions** regularly.

```bash
# agent(s) Agent Engine
python -c "import vertexai; from vertexai import agent_engines; vertexai.init(project='PROJECT_ID',location='REGION'); [a.delete(force=True) for a in agent_engines.list()]"
# connecteur
gcloud alpha agent-identity connectors delete CONNECTOR_NAME --project=PROJECT_ID --location=REGION --quiet
# secrets éventuels + projet dédié
gcloud projects delete PROJECT_ID --quiet
```
And **stop the local servers** (`uvicorn`, `adk web`). **Switch the active network back to a test network.**

---

## Part 10 — What's next (going further)

The lab proves the **approach** (connection, A2A, multi-agent, AdCP) on read-only cases. Leads for
real-world use — each potentially deserving its own article :

- **Response monitoring (eval / quality)** — capture every agent turn (input, tools called,
  output) and **score** it. Two levels : (a) *online* — structured logging of `tool_calls` + verdict
  (success / actionable error / hallucination avoided) via Cloud Logging + a log-based metric ;
  (b) *offline* — a reference set of prompts replayed (`adk eval`) to detect regressions
  (e.g. flash falling back to "code" mode, or an AdCP that goes back to `adcp_create`). Key guardrail already in
  place : the **NETWORK CHECK** and the write ban — to *assert* in the eval.
- **Model choice & cost** — `MODEL` is a user parameter; measure latency/cost/function-calling
  reliability per model on the same prompts (flash vs pro) and document the trade-off.
- **Production auth** — move from the static token to the **Agent Identity connector** (managed 3LO) for
  deployed agents; each user authorizes via the connector (cf the error `Failed to retrieve
  credential` = expected behavior as long as the user hasn't consented).
- **End-to-end AdCP** — from `adcp_preview` (read-only) to `adcp_create` (write) with the
  `confirmation_token`, behind a human guardrail — an "execute a media buy via AdCP" article.
- **Retention & confidentiality** — log retention policy + session purge (Part 9),
  aligned with zero-storage.

---

## 📸 Illustrative screenshots (illustrate what matters, not every step)

A screenshot only serves the **non-obvious moments / proofs** — not every command (the rest = code/terminal
blocks, already in the text). The 6 screenshots that count :

The **web-ready** screenshots (webp, ≤ 1600 px) are in [`captures/web/`](./captures/web/).

⚠️ **The Academy is multilingual** (Svelte pages, bilingual FR/EN text via `$locale`). So the images
are **language-neutral** (blurred identifiers + badge/arrow only, **no baked-in text**) ; the **caption lives in the page**
via the `$locale` ternary. The FR/EN pairs ready to paste are in [`captures/captions.md`](./captures/captions.md).

| # | Illustrates (part) | Screen | `captures/web/` file |
|---|---|---|---|
| 1 | Agent **deployed in the Agent Platform** (P5) | Vertex AI console → Agent Runtime (agent listed, framework `google-adk`) | `01-agent-deploye-agent-platform.webp` — IDs blurred |
| 2b | **The real A2A Agent Card** (P2/P6) | Browser : `http://127.0.0.1:10000/.well-known/agent.json` (card served by `to_a2a`) | `02b-agent-card-a2a.webp` |
| 3 | **OAuth consent** (P3) | Google "Select an account" screen + "signing back in" during `get_token.py` | `03-consentement-oauth-compte.webp` + `03b-consentement-oauth-autoriser.webp` — emails blurred |
| 4 | **Inter-agent A2A communication** (P7) | `adk web` : `registry_search_agents` → `transfer_to_agent` → response from the GAM agent | `04-a2a-communication-inter-agents.webp` |
| 5 | **Async multi-agent** (P8) | `adk web` : `specialists` (forecast ∥ format) → `synthesis_agent` | `05-multi-agents-async.webp` |
| 5bis-a | **"Connect an agent" page** (P5bis) | OrbiAds → Settings → Account → Agents : self-service form | `5bis-connecter-un-agent.webp` — ⚠️ FR overlay to neutralize |
| 5bis-b | **Agent client created** (P5bis) | OrbiAds : `client_id` + one-time secret shown once | `5bis-agent-cree.webp` — ⚠️ FR overlay to neutralize |

To redo/complete yourself (not included, as they are specific to your account) : `2a` the Agent
**Registry** entry (`CUSTOM`), `6` Google's **managed MCP servers**. Always blur project / project number /
network code / ad unit IDs / emails before publishing.

- Screenshots **4 and 5** : take them natively from `http://127.0.0.1:8000` (`orchestrator` and
  `gam_optimizer` apps) → save them in `captures/`.
- Screenshots **2b / 3** : taken by launching the local agent (`uvicorn …:a2a_app --port 10000`) and
  `python get_token.py`.
- ⚠️ **Your console screenshots show your real identifiers** (project, project number, network code, ad unit
  IDs…). To **publish** : blur these areas, or retake the screenshots on a **demo** project/network.
  The tutorial (text) is already 100% generic; it's the images that need cleaning.

## ✅ Checklist (don't forget anything)
- [ ] `gcloud components update` + `install alpha`
- [ ] venv + `google-adk[a2a,agent-identity]` + `mcp` + `opentelemetry==1.42.1`
- [ ] Project + billing linked + 7 APIs enabled (propagation)
- [ ] `gam_sentinel/.env` correct (Vertex model available, auth present) — **this is THE file ADK reads**
- [ ] Token : `get_token.py` (DCR+PKCE+consent) → access **and** refresh in the `.env`
- [ ] Test via `adk run`/`adk web` (not raw JSON-RPC) on a **test network**
- [ ] Agent Engine deployment (vertexai installed, opentelemetry pinned)
- [ ] 3LO connector (iamconnectors API, `CredentialManager.register_auth_provider`)
- [ ] Agent Card served (card = same port as the server) + registered in the registry
- [ ] Orchestrator : `GAM_A2A_CARD_URL` correct + `gam_sentinel` launched over A2A
- [ ] Multi-agent : `{var?}` optional in the synthesis
- [ ] Teardown : agents + connector + project + local servers + test network
