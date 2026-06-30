"""GAM Inventory Sentinel — a narrow, A2A-exposed agent over the OrbiAds MCP.

Mirrors the Google "currency-agent" A2A codelab, but swaps the toy MCP for the
real OrbiAds Google Ad Manager MCP, scoped read-only to an inventory check.

NOTE: ADK import paths shift between releases. If an import fails, run
`python -c "import google.adk; print(google.adk.__version__)"` and adjust.
"""

import os

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.a2a.utils.agent_to_a2a import to_a2a

load_dotenv()

MCP_URL = os.environ.get("ORBIADS_MCP_URL", "https://orbiads.com/mcp")
MODEL = os.environ.get("MODEL", "gemini-2.5-flash")  # sensible default; override in .env
PORT = int(os.environ.get("PORT", os.environ.get("A2A_PORT", "10000")))  # Cloud Run injects PORT


def _persist_rotated_refresh(new_refresh: str) -> None:
    """OrbiAds ROTATES the refresh token on every use. For scale-to-zero to
    survive cold starts, write the rotated token back as a new Secret Manager
    version so the next boot (--set-secrets :latest) reads a valid one.
    No-op locally (no GOOGLE_CLOUD_PROJECT / ORBIADS_REFRESH_SECRET)."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    secret = os.environ.get("ORBIADS_REFRESH_SECRET")
    if not (project and secret):
        return
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        client.add_secret_version(
            parent=f"projects/{project}/secrets/{secret}",
            payload={"data": new_refresh.encode()},
        )
        print(f"[auth] rotated refresh token persisted to secret '{secret}'", flush=True)
    except Exception as exc:  # never crash boot on persistence failure
        print(f"[auth] WARNING refresh persist failed: {exc}", flush=True)


def _read_refresh_from_secret() -> str | None:
    """Agent Engine / Cloud Run: read the refresh token from Secret Manager at
    runtime (ORBIADS_REFRESH_SECRET) instead of baking it into the deployment."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    secret = os.environ.get("ORBIADS_REFRESH_SECRET")
    if not (project and secret):
        return None
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project}/secrets/{secret}/versions/latest"
        return client.access_secret_version(name=name).payload.data.decode()
    except Exception as exc:
        print(f"[auth] WARNING could not read refresh secret: {exc}", flush=True)
        return None


def _resolve_access_token() -> str:
    """Local: use ORBIADS_MCP_TOKEN directly.
    Headless (Cloud Run / Agent Engine): mint a fresh access token from the
    refresh token — read from env or Secret Manager — no browser ever needed.
    """
    static = os.environ.get("ORBIADS_MCP_TOKEN", "")
    if static:
        return static
    refresh = os.environ.get("ORBIADS_MCP_REFRESH_TOKEN") or _read_refresh_from_secret()
    client_id = os.environ.get("ORBIADS_MCP_CLIENT_ID")
    if not (refresh and client_id):
        return ""
    import json
    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id}
    ).encode()
    req = urllib.request.Request(
        MCP_URL.rstrip("/") + "/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        tok = json.loads(r.read().decode())
    new_refresh = tok.get("refresh_token")
    if new_refresh and new_refresh != refresh:
        _persist_rotated_refresh(new_refresh)
    return tok["access_token"]


# --- Auth modes ---
# Clean mode (Agent Engine): Agent Identity Auth Manager via a 3LO connector.
# Fallback (local/Cloud Run): bearer minted from refresh token.
CONNECTOR = os.environ.get("ORBIADS_CONNECTOR")  # projects/.../connectors/orbiads
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]

# --- THE CORE: "scoping the skills" = tool_filter, centered on THE CONNECTION ---
# Layer 1 (agent->OrbiAds) = bearer above. Layer 2 (OrbiAds->GAM) = these connection
# tools exposed by the MCP. This is the only OrbiAds-specific part of the tutorial.
# Confirm the exact names via tools/list on the live MCP.
CONNECTION_TOOLS = [
    "get_my_tenant_id",     # who am I / gamStatus
    "check_credentials",    # state: NOT_CONNECTED / PENDING_NETWORK_SELECTION / CONNECTED_READY ...
    "initiate_gam_auth",    # (re)connect GAM if NOT_CONNECTED / DESYNC
    "poll_auth_status",     # wait for the GAM OAuth flow to finish
    "select_gam_network",   # pick the networkCode if PENDING_NETWORK_SELECTION
    "inventory",            # the read-only task once CONNECTED_READY
]

if CONNECTOR:
    from google.adk.integrations.agent_identity import GcpAuthProvider, GcpAuthProviderScheme
    from google.adk.auth.credential_manager import CredentialManager

    _scheme = GcpAuthProviderScheme(name=CONNECTOR, scopes=SCOPES)
    # Register on the framework's class-level singleton (NOT a fresh AuthProviderRegistry()).
    CredentialManager.register_auth_provider(GcpAuthProvider())
    orbiads_mcp = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(url=MCP_URL),
        tool_filter=CONNECTION_TOOLS,
        auth_scheme=_scheme,
    )
else:
    _token = _resolve_access_token()
    _headers = {"Authorization": f"Bearer {_token}"} if _token else {}
    orbiads_mcp = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(url=MCP_URL, headers=_headers),
        tool_filter=CONNECTION_TOOLS,
    )

root_agent = LlmAgent(
    name="gam_inventory_sentinel",
    model=MODEL,
    description="Connects OrbiAds to GAM, then monitors inventory availability (read-only).",
    instruction=(
        "You are a READ-ONLY GAM inventory sentinel.\n"
        "CONNECTION FIRST: call check_credentials.\n"
        "- If state == CONNECTED_READY or CONNECTED_READ_ONLY -> continue.\n"
        "- If PENDING_NETWORK_SELECTION -> call select_gam_network with one of availableNetworks.\n"
        "- If NOT_CONNECTED or PERMISSIONS_DESYNC -> call initiate_gam_auth, then poll_auth_status, "
        "and show the authorization link to the user.\n"
        "NETWORK CHECK (safety): from check_credentials read networkCode + networkDisplayName and STATE "
        "THEM to the user. If autoBound is true, or the active network is not the one the user intends, "
        "STOP and ask for confirmation before doing anything else. Never operate on an unexpected "
        "(possibly production) network.\n"
        "Once connected AND the network is confirmed: (1) inspect inventory (ad units), (2) flag "
        "low-availability units, (3) summarize in a short report. You NEVER write (no create/update)."
    ),
    tools=[orbiads_mcp],
)

# --- A2A: auto-generates /.well-known/agent-card.json from the filtered tools ---
a2a_app = to_a2a(root_agent, port=PORT)
