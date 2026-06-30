"""Multi-agent business case: GAM delivery optimization plan.

Two specialists run IN PARALLEL (async), then a synthesis merges them:
  Forecast (impression potential) || Format/CTR (best formats) -> Synthesis
All via the real OrbiAds tools (reporting/inventory/formats), read-only.
"""

import os

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

_NO_CODE = (
    "ABSOLUTE TOOL-CALLING RULE: use ONLY the native function-calling mechanism. "
    "NEVER emit code (no print(...), no python block, no invented namespace like "
    "ad_platform.x / forecasting.x / reporting.x). Call tools directly by their real name "
    "(check_credentials, reporting, inventory, formats) with their JSON parameters.\n"
)

_NETWORK_CHECK = (
    "NETWORK CHECK (safety): from check_credentials, read networkCode + networkDisplayName and state "
    "them at the start of your answer. If autoBound is true or the active network is not the intended "
    "one, STOP and flag it instead of running reads — never read from an unexpected (possibly "
    "production) network.\n"
)

MCP_URL = os.environ.get("ORBIADS_MCP_URL", "https://orbiads.com/mcp")
TOKEN = os.environ.get("ORBIADS_MCP_TOKEN", "")
MODEL = os.environ.get("MODEL", "gemini-2.5-flash")
_HDR = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


def _mcp(tool_filter):
    return MCPToolset(
        connection_params=StreamableHTTPConnectionParams(url=MCP_URL, headers=_HDR),
        tool_filter=tool_filter,
    )


# --- Specialist 1: delivery potential (forecast) ---
forecast_agent = LlmAgent(
    name="forecast_agent",
    model=MODEL,
    description="Estimates the delivery potential (available impressions) of the GAM inventory.",
    instruction=(
        _NO_CODE + _NETWORK_CHECK +
        "You estimate DELIVERY POTENTIAL, READ-ONLY.\n"
        "1) check_credentials (then apply the NETWORK CHECK above).\n"
        "2) via reporting, call get_traffic_data for available/historical impressions (~30 days). "
        "This is your primary source because it needs no line item.\n"
        "3) get_standalone_forecast / get_prospective_delivery_forecast REQUIRE a line item SPEC "
        "(targeting, size, dates). Call them ONLY if such a spec was provided. Otherwise DO NOT call them.\n"
        "4) Report the number ACTUALLY returned by the tool. If get_traffic_data returns nothing and no "
        "forecast spec was provided, write exactly: 'Potential not quantifiable: no traffic data and no "
        "line item spec provided.' "
        "NEVER invent a number (no round figures like 5,000,000 out of nowhere). NEVER write to GAM."
    ),
    tools=[_mcp(["check_credentials", "reporting", "inventory"])],
    output_key="forecast_result",
)

# --- Specialist 2: format recommendation (CTR) ---
format_agent = LlmAgent(
    name="format_agent",
    model=MODEL,
    description="Recommends formats to maximize CTR and flags obsolete sizes.",
    instruction=(
        _NO_CODE + _NETWORK_CHECK +
        "You recommend FORMATS to maximize CTR, READ-ONLY.\n"
        "STEPS (actually call the tools, invent no tool name):\n"
        "1) check_credentials (then apply the NETWORK CHECK above).\n"
        "2) CTR by size: reporting with action='run_custom_report', "
        "dimensions=['AD_REQUEST_SIZES'], metrics=['IMPRESSIONS','CLICKS']. "
        "CTR = CLICKS/IMPRESSIONS, compute it yourself per size. Do NOT use CREATIVE_SIZE (rejected in REST).\n"
        "3) Present sizes: inventory with action='list_ad_unit_sizes' (NO other parameter). "
        "It returns a list of objects {width,height,isAspectRatio,fullDisplayString}. "
        "An entry with width=0/height=0 (empty fullDisplayString) = ASPECT-RATIO/fluid size (responsive); "
        "this is NOT an obsolete size: report it as 'responsive', do not discard it.\n"
        "4) Obsolescence = YOUR judgment: compare each non-empty fullDisplayString to this heuristic list of "
        "legacy formats { '468x60','234x60','120x600','160x600 if unsold','88x31','120x60' } and list those "
        "actually present in the inventory. NEVER send this list to a tool.\n"
        "5) Output: top formats by CTR (real numbers) + sizes to retire (actually present). "
        "If data is missing, say so plainly (e.g. 'no clicks over 30 days'). "
        "FORBIDDEN: bracketed placeholders like [CTR_DATA_HERE]. NEVER write to GAM."
    ),
    tools=[_mcp(["check_credentials", "reporting", "inventory", "formats"])],
    output_key="format_result",
)

# --- PARALLEL (async) run of both specialists ---
specialists = ParallelAgent(name="specialists", sub_agents=[forecast_agent, format_agent])

# --- Synthesis: merges both results into an actionable recommendation ---
# AdCP (#4): do NOT hand-roll an AdCP brief here. OrbiAds already exposes a native
# AdCP surface via dedicated MCP tools — use those instead of inventing a shape:
#   - get_products_adcp           (sell-side discovery, read-only)
#   - validate_adcp_request       (validate create_media_buy vs v3 schema, read-only)
#   - preview_media_buy_from_adcp (translate AdCP request -> DealSpec, read-only)
#   - create_media_buy_from_adcp  (execute end-to-end, write)
# This synthesis stays a plain human-readable plan; the canonical AdCP demo is a
# separate read-only flow (buy agent sends an AdCP request -> validate -> preview).
synthesis_agent = LlmAgent(
    name="synthesis_agent",
    model=MODEL,
    description="Merges forecast + format reco into an actionable optimization plan.",
    instruction=(
        "Build a short, actionable DELIVERY OPTIMIZATION PLAN from:\n"
        "- Potential (forecast): {forecast_result?}\n"
        "- Formats (CTR): {format_result?}\n"
        "Give: (1) estimated potential, (2) formats to prioritize, (3) sizes to retire. "
        "Stay factual; if data is missing, say so in one sentence. "
        "FORBIDDEN: copying bracketed placeholders (e.g. [CTR_DATA_HERE]) — either a real value or an "
        "explicit 'data missing'. Do NOT emit a fabricated AdCP/JSON brief; AdCP is handled by OrbiAds' "
        "dedicated tools, not by this agent."
    ),
)

root_agent = SequentialAgent(
    name="gam_optimizer",
    sub_agents=[specialists, synthesis_agent],
)
