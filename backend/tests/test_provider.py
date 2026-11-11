import asyncio
import httpx
import pytest
from app.llm import OpenAICompatibleProvider, ProviderUnavailable
from app.schemas import Answer

def test_provider_schema_and_retry(monkeypatch):
    calls=[]
    class FakeClient:
        def __init__(self,**kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*a): pass
        async def post(self,url,**kw):
            calls.append(kw['json'])
            content='not-json' if len(calls)==1 else '{"text":"均衡饮食"}'
            return httpx.Response(200,json={'choices':[{'message':{'content':content}}]},request=httpx.Request('POST',url))
    monkeypatch.setenv('LLM_API_KEY','test-only')
    monkeypatch.setattr('app.llm.httpx.AsyncClient',FakeClient)
    result=asyncio.run(OpenAICompatibleProvider().generate('test',Answer))
    assert result.text=='均衡饮食' and len(calls)==2
    assert calls[0]['response_format']['type']=='json_schema'

def test_no_key(monkeypatch):
    monkeypatch.delenv('LLM_API_KEY',raising=False)
    with pytest.raises(ProviderUnavailable): asyncio.run(OpenAICompatibleProvider().generate('test',Answer))

def test_tool_allowlist(monkeypatch):
    from app.llm import plan_tools
    class FakeClient:
        def __init__(self,**kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*a): pass
        async def post(self,url,**kw):
            return httpx.Response(200,json={'choices':[{'message':{'tool_calls':[{'function':{'name':'food_log','arguments':'{}'}}]}}]},request=httpx.Request('POST',url))
    monkeypatch.setenv('LLM_API_KEY','test-only')
    monkeypatch.setattr('app.llm.httpx.AsyncClient',FakeClient)
    with pytest.raises(ProviderUnavailable): asyncio.run(plan_tools(None,'test',['nutrition_search']))
    assert asyncio.run(plan_tools(None,'test',['food_log']))==['food_log']
