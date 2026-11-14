'use client';
import {useEffect,useRef,useState} from 'react';
import {Mic,Square} from 'lucide-react';
type Recognition={lang:string;interimResults:boolean;onresult:((event:{results:{[key:number]:{[key:number]:{transcript:string}}};resultIndex:number})=>void)|null;onerror:((event:{error:string})=>void)|null;onend:(()=>void)|null;start:()=>void;stop:()=>void;abort:()=>void};
type VoiceWindow=Window&{SpeechRecognition?:new()=>Recognition;webkitSpeechRecognition?:new()=>Recognition};
export function VoiceInput({onText,disabled}:{onText:(text:string)=>void;disabled:boolean}){
 const ref=useRef<Recognition|null>(null),[supported,setSupported]=useState(false),[recording,setRecording]=useState(false),[message,setMessage]=useState('');
 useEffect(()=>{const w=window as VoiceWindow;setSupported(!!(w.SpeechRecognition||w.webkitSpeechRecognition));return()=>ref.current?.abort()},[]);
 function start(){if(recording){ref.current?.stop();return}const w=window as VoiceWindow;const C=w.SpeechRecognition||w.webkitSpeechRecognition;if(!C)return;
  if(!window.confirm('允许使用浏览器语音识别？麦克风权限由浏览器请求，声音可能由浏览器服务处理；识别文字可编辑，不会自动发送。'))return;
  const r=new C();ref.current=r;r.lang='zh-CN';r.interimResults=false;r.onresult=e=>{onText(e.results[e.resultIndex][0].transcript);setMessage('已转为文字，请检查后发送。')};r.onerror=e=>{setMessage(e.error==='not-allowed'?'麦克风授权被拒绝，可继续打字。':'语音识别失败，可重试或打字。');setRecording(false)};r.onend=()=>setRecording(false);try{r.start();setRecording(true)}catch{setMessage('无法启动语音，请继续输入文字。')}
 }
 return <div className="voice-control">{supported?<button type="button" className="ghost" aria-pressed={recording} disabled={disabled} onClick={start}>{recording?<Square size={16}/>:<Mic size={16}/>} {recording?'停止录音':'语音输入'}</button>:<small>此浏览器不支持语音，可直接打字</small>}{message&&<small role="status">{message}</small>}</div>
}
