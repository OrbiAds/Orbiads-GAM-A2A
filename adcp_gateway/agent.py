"""AdCP gateway — a READ-ONLY agent that ingests an AdCP create_media_buy
request and previews it as GAM deals, WITHOUT executing.

This is the canonical "buy-side agent talks to a sell-side agent" story:
  buy agent --(AdCP create_media_buy)--> adcp_gateway
      -> validate_adcp_request        (schema v3 check, read-only, 0 credit)
      -> preview_media_buy_from_adcp  (translate to DealSpec, read-only, no GAM write)

It uses OrbiAds' NATIVE AdCP tools — no hand-rolled brief shape. The AdCP façade
lives under the `deals` PARENT tool, discriminated by `action`:
  deals(action="adcp_validate", params={request})  -> schema v3 check  (read-only)
  deals(action="adcp_preview",  params={request})  -> translate -> DealSpec (read-only)
  deals(action="adcp_create",   params={request})  -> EXECUTE (write) — FORBIDDEN here

CAVEAT (worth knowing): ADK's `tool_filter` scopes by tool NAME, not by action.
Since the read-only AdCP actions live under the `deals` parent, exposing `deals`
also technically exposes its write actions. We rely on (a) the instruction below
and (b) OrbiAds' own confirmation-token gate (adcp_create refuses to run without
a token returned by a prior preview). For HARD read-only you'd need a server-side
read-only scope.
"""

import os

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

MCP_URL = os.environ.get("ORBIADS_MCP_URL", "https://orbiads.com/mcp")
TOKEN = os.environ.get("ORBIADS_MCP_TOKEN", "")
MODEL = os.environ.get("MODEL", "gemini-2.5-flash")
_HDR = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

_NO_CODE = (
    "ABSOLUTE TOOL-CALLING RULE: use ONLY the native function-calling mechanism. "
    "NEVER emit code (no print(...), no python block, no invented namespace). Call tools "
    "directly by their real name (check_credentials, deals) with their JSON parameters.\n"
)

_NETWORK_CHECK = (
    "NETWORK CHECK (safety): from check_credentials, read networkCode + networkDisplayName and state "
    "them at the start of your answer. If autoBound is true or the active network is not the intended "
    "one, STOP and flag it instead of proceeding — never operate on an unexpected (possibly "
    "production) network.\n"
)

orbiads_mcp = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(url=MCP_URL, headers=_HDR),
    # AdCP façade lives under the `deals` parent (see module docstring CAVEAT).
    tool_filter=["check_credentials", "deals"],
)

root_agent = LlmAgent(
    name="adcp_gateway",
    model=MODEL,
    description="Ingests an AdCP create_media_buy request and previews it as GAM deals (read-only).",
    instruction=(
        _NO_CODE + _NETWORK_CHECK +
        "You are an AdCP gateway, READ-ONLY. A buy-side agent (or the user) gives you an AdCP "
        "create_media_buy JSON request.\n"
        "You may ONLY call: check_credentials, and deals with action 'adcp_validate' or 'adcp_preview'. "
        "You must NEVER call deals(action='adcp_create') or any other write action — previewing only.\n"
        "STEPS:\n"
        "1) check_credentials (then apply the NETWORK CHECK above).\n"
        "2) deals(action='adcp_validate', params={request: <the AdCP JSON>}). If valid is false, list the "
        "schema errors plainly and STOP — do not preview an invalid payload.\n"
        "3) If valid, deals(action='adcp_preview', params={request: <the AdCP JSON>}) to translate it into "
        "GAM DealSpec(s) WITHOUT executing.\n"
        "4) Summarize for a human: is it valid? deal type (pmp_auction / pg_guaranteed / pd_preferred), "
        "brand, package count, and either the GAM deal(s) that WOULD be created or the actionable error "
        "(e.g. ADCP_ADVERTISER_UNRESOLVED -> the buyer must supply ext.orbiads_advertiser_company_id). "
        "Make clear nothing was written to GAM. If a tool errors, report the error verbatim; never invent a result."
    ),
    tools=[orbiads_mcp],
)
