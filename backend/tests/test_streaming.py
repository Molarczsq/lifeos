import asyncio
import json
import httpx
import pytest
from app.llm import partial_text, stream_answer, ProviderUnavailable

def test_partial_json_text():
    assert partial_text('{"text":"你好')=='你好'
    assert partial_text('{"text":"hi\\nthere')=='hi\nthere'
    assert partial_text('{"text":"hi\\u4')=='hi'
    assert partial_text('{"text":"hi\\" there')=='hi" there'
    assert partial_text('{"other":"secret')==''

@pytest.mark.parametrize('finish,valid', [('stop',True),('length',False)])
def test_provider_sse_contract(monkeypatch,finish,valid):
    data=''
    for part in ['{"text":"','你好','"}']:
        data+='data: '+json.dumps({'choices':[{'delta':{'content':part},'finish_reason':None}]})+'\n\n'
    data+='data: '+json.dumps({'choices':[{'delta':{},'finish_reason':finish}]})+'\n\n'
    data+='data: [DONE]\n\n'
    def handler(request):
        payload=json.loads(request.content)
        assert payload['stream'] and payload['response_format']['type']=='json_object'
        return httpx.Response(200,text=data)
    original=httpx.AsyncClient
    monkeypatch.setattr('app.llm.httpx.AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setenv('LLM_API_KEY','test-key')
    monkeypatch.setenv('LLM_BASE_URL','https://api.deepseek.com')
    async def run():return [event async for event in stream_answer('你好')]
    if valid:
        events=asyncio.run(run())
        assert events[-1]=={'type':'validated','text':'你好'}
        assert any(e['type']=='draft' for e in events)
    else:
        with pytest.raises(ProviderUnavailable):asyncio.run(run())
