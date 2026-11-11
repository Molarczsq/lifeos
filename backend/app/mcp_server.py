"""Read-only stdio MCP tools; no personal health data is exposed."""
from mcp.server.fastmcp import FastMCP
from .agents import search, FOODS
mcp=FastMCP('LifeOS knowledge')
@mcp.tool()
def search_knowledge(query:str)->list:
    """Search cited general dietary education, using lexical retrieval."""
    return search(query[:2000])
@mcp.tool()
def food_catalog()->dict:
    """Return illustrative food estimates, not verified measured nutrition."""
    return {'status':'demo-estimates','foods':FOODS}
if __name__=='__main__': mcp.run(transport='stdio')
