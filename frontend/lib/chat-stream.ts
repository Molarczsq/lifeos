export type ChatEvent={type:string;id?:string;name?:string;text?:string;mode?:string;citations?:{id:string;title:string;url:string}[]};
export async function streamChat(body:Record<string,unknown>,signal:AbortSignal,onEvent:(event:ChatEvent)=>void){
 const response=await fetch('/api/v1/advisor/chat/stream',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
 if(!response.ok||!response.body){const error=await response.json().catch(()=>null);throw new Error(typeof error?.detail==='string'?error.detail:'对话暂时不可用，请重试');}
 const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',complete=false;
 try{while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let index;while((index=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,index);buffer=buffer.slice(index+2);const data=frame.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');if(!data)continue;const event=JSON.parse(data) as ChatEvent;if(event.type==='error')throw new Error(event.text||'生成失败');if(event.type==='done')complete=true;onEvent(event);}}if(!complete)throw new Error('连接中断，请先刷新历史确认结果，再重试');}
 finally{reader.releaseLock();}
}
