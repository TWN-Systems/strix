"""Strix MCP - Model Context Protocol integration.

This package provides:
- MCP Gateway for zen-mcp-server integration
- Multi-model consensus and validation
- Automated execution pipelines
- AI-powered planning and review

Usage:
    from strix.mcp import MCPGateway, get_mcp_gateway

    # Get the gateway
    gateway = get_mcp_gateway()

    # Use consensus for validation
    result = await gateway.consensus(
        prompt="Is this vulnerability exploitable?",
        context=finding_details
    )

    # Create and run a pipeline
    from strix.mcp import ExecutionPipeline, create_reconnaissance_pipeline

    pipeline = create_reconnaissance_pipeline(target="192.168.1.1")
    results = await pipeline.execute()
    insights = await pipeline.review_with_ai(results)

Environment Variables:
    ZEN_MCP_ENABLED: Enable zen-mcp integration
    ZEN_MCP_TRANSPORT: Transport type (stdio, http)
    ZEN_MCP_COMMAND: Command to start zen-mcp-server
"""

from strix.mcp.gateway import (
    MCPConfig,
    MCPGateway,
    MCPResult,
    MCPTool,
    get_mcp_gateway,
    set_mcp_gateway,
)
from strix.mcp.pipeline import (
    ExecutionPipeline,
    PipelineResult,
    PipelineStage,
    PlanItem,
    PlanItemStatus,
    StageStatus,
    create_reconnaissance_pipeline,
)


__all__ = [
    # Gateway
    "MCPConfig",
    "MCPGateway",
    "MCPResult",
    "MCPTool",
    "get_mcp_gateway",
    "set_mcp_gateway",
    # Pipeline
    "ExecutionPipeline",
    "PipelineResult",
    "PipelineStage",
    "PlanItem",
    "PlanItemStatus",
    "StageStatus",
    "create_reconnaissance_pipeline",
]
