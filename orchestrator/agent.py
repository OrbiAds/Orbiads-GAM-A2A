"""Orchestrator — discovers the GAM agent (registry) then delegates to it over A2A.

Reproduces the "A2A & Agent Registry" pattern:
  registry_search_agents  -> finds "GAM Inventory Sentinel"
  call_remote_a2a_agent   -> RemoteA2aAgent delegates the task over A2A.
"""

import os

from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.tools import FunctionTool
from google.adk.integrations.agent_registry import AgentRegistry

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-gcp-project")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
GAM_A2A_CARD = os.environ.get(
    "GAM_A2A_CARD_URL", "http://127.0.0.1:10000/.well-known/agent-card.json"
)

_reg = AgentRegistry(project_id=PROJECT, location=LOCATION)


def registry_search_agents(need: str) -> list[dict]:
    """Search the Agent Registry for A2A agents available for a given need."""
    res = _reg.list_agents()
    return [
        {"name": a.get("displayName"), "id": a.get("name")}
        for a in res.get("agents", [])
    ]


# The remote sub-agent called over A2A (the video's `call_remote_a2a_agent`).
gam_remote = RemoteA2aAgent(
    name="gam_inventory_sentinel",
    description="Specialized GAM agent (inventory, read-only) reached over A2A.",
    agent_card=GAM_A2A_CARD,
)

root_agent = LlmAgent(
    name="orchestrator",
    model=os.environ.get("MODEL", "gemini-2.5-flash"),
    description="Orchestrator: discovers agents in the Agent Registry and delegates over A2A.",
    instruction=(
        "You are an orchestrator. For any request related to Google Ad Manager or ad inventory: "
        "(1) call registry_search_agents to surface the available specialized agent, "
        "(2) delegate the task to the gam_inventory_sentinel sub-agent, (3) return its answer."
    ),
    tools=[FunctionTool(registry_search_agents)],
    sub_agents=[gam_remote],
)
