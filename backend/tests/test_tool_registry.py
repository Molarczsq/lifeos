import asyncio,json
import httpx
import pytest
from app.agent_tools import plan_calls
from app.llm import ProviderUnavailable,USAGE_EVENTS,record_usage
from app.db import User

def test_function_calling_validates_arguments_and_permission(monkeypatch):
    async def request(self,url,**kwargs):
        assert kwargs['json']['tools'][0]['type']=='function'
        return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'tool_calls':[{'function':{'name':'get_food_nutrition','arguments':'{"name":"糙米饭","prepare_meal":true}'}}]}}]})
    monkeypatch.setattr(httpx.AsyncClient,'post',request)
    u=User(id='one',username='u',password='x',consents={'diet':True})
    result=asyncio.run(plan_calls('记饭',[],u));assert result[0][1].prepare_meal
    async def invalid(self,url,**kwargs):
        return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'tool_calls':[{'function':{'name':'add_meal','arguments':'{"items":[{"food_id":"rice","grams":100}]}'}}]}}]})
    monkeypatch.setattr(httpx.AsyncClient,'post',invalid);u.consents={}
    with pytest.raises(ProviderUnavailable):asyncio.run(plan_calls('记饭',[],u))

def test_usage_unknown_is_not_zero_cost(monkeypatch):
    data=[];token=USAGE_EVENTS.set(data)
    try:
        record_usage(None,'stream');assert data[0]['estimated_cost_usd'] is None
        monkeypatch.setenv('LLM_INPUT_USD_PER_MILLION','1');monkeypatch.setenv('LLM_OUTPUT_USD_PER_MILLION','2')
        record_usage({'prompt_tokens':100,'completion_tokens':50},'generate')
        assert data[1]['estimated_cost_usd']==.0002
    finally:USAGE_EVENTS.reset(token)
