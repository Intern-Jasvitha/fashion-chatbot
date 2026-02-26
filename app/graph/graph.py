"""LangGraph orchestration: build and compile the agent graph with PostgresSaver checkpointer."""

import logging
from functools import partial
from typing import Literal

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.graph.nodes import (
    hybrid_node,
    intent_router_node,
    policy_gate_node,
    rag_node,
    sql_node,
)
from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def _route_by_intent(state: AgentState) -> Literal["sql_agent", "rag_agent", "hybrid_agent"]:
    """Route to the appropriate agent node based on detected intent."""
    intent = state.get("intent") or "hybrid"
    if intent == "sql":
        return "sql_agent"
    if intent == "rag":
        return "rag_agent"
    return "hybrid_agent"


def _route_after_policy(state: AgentState) -> Literal["intent_router", "end"]:
    """Route to intent router only when policy gate allows the request."""
    allow = state.get("policy_allow")
    if allow is True:
        return "intent_router"
    return "end"


def build_graph(
    settings: Settings,
    qdrant_client: QdrantClient,
    checkpointer: AsyncPostgresSaver,
):
    """Build and compile the LangGraph agent orchestrator."""
    builder = StateGraph(AgentState)

    # Bind settings and qdrant to node kwargs
    intent_node = partial(intent_router_node, settings=settings)
    policy_node = partial(policy_gate_node, settings=settings)
    sql_node_bound = partial(sql_node, settings=settings, qdrant_client=qdrant_client)
    rag_node_bound = partial(rag_node, settings=settings, qdrant_client=qdrant_client)
    hybrid_node_bound = partial(hybrid_node, settings=settings, qdrant_client=qdrant_client)

    builder.add_node("policy_gate", policy_node)
    builder.add_node("intent_router", intent_node)
    builder.add_node("sql_agent", sql_node_bound)
    builder.add_node("rag_agent", rag_node_bound)
    builder.add_node("hybrid_agent", hybrid_node_bound)

    builder.add_edge(START, "policy_gate")
    builder.add_conditional_edges(
        "policy_gate",
        _route_after_policy,
        {
            "intent_router": "intent_router",
            "end": END,
        },
    )
    builder.add_conditional_edges(
        "intent_router",
        _route_by_intent,
        {
            "sql_agent": "sql_agent",
            "rag_agent": "rag_agent",
            "hybrid_agent": "hybrid_agent",
        },
    )
    builder.add_edge("sql_agent", END)
    builder.add_edge("rag_agent", END)
    builder.add_edge("hybrid_agent", END)

    graph = builder.compile(checkpointer=checkpointer)
    logger.info("LangGraph agent orchestrator compiled with PostgresSaver checkpointer")
    return graph
