from fastmcp import FastMCP
mcp = FastMCP("Calculator Server")
@mcp.tool
def add(a: int, b: int) -> int:
    """Adds two numbers."""
    return a + b

if __name__ == "__main__":
    mcp.run()