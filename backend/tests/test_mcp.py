import asyncio
from app.mcp_server import mcp

def test_mcp_discovery_and_call():
    async def check():
        tools=await mcp.list_tools()
        assert {t.name for t in tools}=={'search_knowledge','food_catalog'}
        result=await mcp.call_tool('search_knowledge',{'query':'蔬菜'})
        assert result
    asyncio.run(check())
