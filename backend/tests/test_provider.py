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

@pytest.mark.parametrize('base,mode,expected', [
    ('https://api.deepseek.com', 'auto', 'json_object'),
    ('https://api.deepseek.com/v1', 'auto', 'json_object'),
    ('https://example.org/v1', 'auto', 'json_schema'),
    ('https://example.org/v1', 'json_object', 'json_object'),
])
def test_response_format_selection(monkeypatch, base, mode, expected):
    from app.llm import response_format
    monkeypatch.setenv('LLM_BASE_URL', base)
    monkeypatch.setenv('LLM_RESPONSE_FORMAT', mode)
    assert response_format(Answer)['type'] == expected

@pytest.mark.parametrize('content,valid', [('{"text":"你好"}', True), ('{"unexpected":"private-health-data"}', False)])
def test_deepseek_json_object_validates_locally(monkeypatch, caplog, content, valid):
    calls=[]
    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, **kw):
            payload=kw['json']; calls.append(payload)
            assert payload['response_format']=={'type':'json_object'}
            assert isinstance(payload['messages'][1]['content'], str)
            assert '"required": ["text"]' in payload['messages'][0]['content']
            return httpx.Response(200, json={'choices':[{'message':{'content':content}}]}, request=httpx.Request('POST',url))
    monkeypatch.setenv('LLM_API_KEY','secret-test-key')
    monkeypatch.setenv('LLM_BASE_URL','https://api.deepseek.com')
    monkeypatch.setenv('LLM_RESPONSE_FORMAT','auto')
    monkeypatch.setattr('app.llm.httpx.AsyncClient',FakeClient)
    if valid:
        assert asyncio.run(OpenAICompatibleProvider().generate('test',Answer)).text=='你好'
    else:
        with pytest.raises(ProviderUnavailable):
            asyncio.run(OpenAICompatibleProvider().generate('test',Answer))
        assert len(calls)==2
        assert 'ValidationError' in caplog.text
        assert 'private-health-data' not in caplog.text
        assert 'secret-test-key' not in caplog.text

def test_http_error_logs_only_category_and_status(monkeypatch, caplog):
    from app.llm import log_failure
    request=httpx.Request('POST','https://example.org',headers={'Authorization':'secret-key'})
    response=httpx.Response(401,request=request,text='private response')
    log_failure('generate',httpx.HTTPStatusError('secret-key',request=request,response=response))
    assert 'http_status=401' in caplog.text
    assert 'secret-key' not in caplog.text and 'private response' not in caplog.text
