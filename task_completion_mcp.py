#!/usr/bin/env python3
"""Task completion MCP server for WebArena benchmark."""

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("task-completion")

@mcp.tool()
async def complete_task(finalAnswer: str) -> str:
    """Signal task completion and provide the final answer.

    Args:
        finalAnswer: Your final answer/result for the task
    """
    return f"TASK_COMPLETE:{finalAnswer}"

if __name__ == "__main__":
    # Run the server using stdio transport
    mcp.run(transport='stdio')
