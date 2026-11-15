import json,os
from fastapi import HTTPException
from .ai_services import rows,put,revision,context,owned,plan
from .agent_tools import plan_calls,execute
from .agents import safety,review_answer
from .knowledge import search
from .llm import stream_answer,OpenAICompatibleProvider,ProviderUnavailable,USAGE_EVENTS
from .schemas import Answer
from .media import owned_image,image_url
from .db import Record,Conversation
from sqlalchemy import select
class GenerativeAdvisor:
 async def run(self,body,u,s,request=None):
    rev=revision(s,u);blocked=safety(body.message)
    history=[{'question':r.data['question'],'answer':r.data['text']} for r in rows(s,u,'chat') if r.data.get('conversation_id')==body.conversation_id and r.data.get('consent_revision')==rev and r.id!=body.regenerate_id][-6:]
    docs=search(body.message);actions=[];navigation=[];results={};events=[];token=USAGE_EVENTS.set(events)
    answer=blocked or 'AI当前不可用。你仍可查看食物知识、手动记录，或检查外部AI授权后重试。';mode='safety' if blocked else 'unavailable'
    try:
      if not blocked and u.consents.get('external_ai') and os.getenv('LLM_API_KEY'):
        yield {'type':'step','name':'检查授权与会话范围'}
        try:
          calls=await plan_calls(body.message,history,u)
          yield {'type':'step','name':'已收到并校验模型工具调用'}
          for round_index in range(2):
            for name,args in calls:
              yield {'type':'step','name':'开始执行工具：'+name}
              try:
                if name=='plan_recipe':
                  if any(k.startswith('plan_recipe:') for k in results):raise HTTPException(422,'每轮只生成一个菜谱方案')
                  result=await plan(args,u,s)
                else:result=execute(name,args,u,s,body.conversation_id)
                results[name+':'+str(len(results))]=result
                if result.get('action'):actions.append(result['action'])
                if result.get('navigation'):navigation.append(result['navigation'])
                if result.get('documents'):docs=result['documents']
                yield {'type':'step','name':'已完成工具：'+name}
              except (HTTPException,ValueError) as e:
                results[name+':'+str(len(results))]={'error':e.detail if isinstance(e,HTTPException) else '参数无效'}
                yield {'type':'step','name':'工具失败：'+name+'，未执行数据修改'}
            if round_index==0 and not actions and any(name=='get_food_nutrition' and args.prepare_meal for name,args in calls):
              calls=await plan_calls(body.message,history,u,results)
              yield {'type':'step','name':'根据查询结果继续规划待确认操作'}
            else:break
        except ProviderUnavailable:
          yield {'type':'step','name':'工具规划不可用，仅基于已授权上下文回答'}
        prompt=json.dumps({'question':body.message,'history_same_consent_revision':history,'authorized_context':{**context(s,u),'selected_plan':owned(s,u,body.plan_id,'plan').data if body.plan_id and u.consents.get('diet') else None,'selected_meal':owned(s,u,body.meal_id,'food').data if body.meal_id and u.consents.get('diet') else None},'actual_tool_results':results,'evidence':docs,'policy':'动作仅待确认，禁止声称已记录。未知营养不得伪造实测值。根据plan_recipe真实结果解释菜谱，确认卡片才是保存入口。'},ensure_ascii=False)
        try:
          image=image_url(owned_image(s,u,body.image_id)) if body.image_id else None
          if body.stream:
            final=None
            async for chunk in stream_answer(prompt,image):
              if request and await request.is_disconnected():return
              if chunk['type']=='draft':
                if not review_answer(chunk['text']):yield chunk
              else:final=chunk['text']
            if final is None:raise ProviderUnavailable('输出不完整')
          else:final=(await OpenAICompatibleProvider().generate(prompt,Answer,image)).text
          checked=review_answer(final);answer=checked or final;mode='safety' if checked else 'live-model'
        except ProviderUnavailable:
          yield {'type':'draft','text':''}
          yield {'type':'step','name':'流式输出未通过校验，重新请求结构化回答'}
          try:
            final=(await OpenAICompatibleProvider().generate(prompt,Answer,image)).text
            checked=review_answer(final);answer=checked or final;mode='safety' if checked else 'live-model'
          except ProviderUnavailable:
            answer='模型当前不可用，未生成AI建议。请稍后重试；待确认操作尚未写入饮食记录。';mode='unavailable'
      if request and await request.is_disconnected():return
      if revision(s,u)!=rev:
        yield {'type':'error','text':'授权已变更，请重新发送问题'}
        return
      if not s.scalar(select(Conversation.id).where(Conversation.id==body.conversation_id,Conversation.user_id==u.id)):return
      if mode=='safety':actions=[];navigation=[]
      result={'text':answer,'mode':mode,'citations':docs if not blocked else [],'actions':actions,'navigation':navigation}
      if body.regenerate_id:
        old=s.get(Record,body.regenerate_id)
        if old:s.delete(old)
      put(s,u,'chat',{'question':body.message,**result,'consent_revision':rev,'conversation_id':body.conversation_id,'image_id':body.image_id})
      yield {'type':'answer',**result}
    finally:
      USAGE_EVENTS.reset(token)
      if events:put(s,u,'ai-usage',{'task':'advisor','calls':events})
