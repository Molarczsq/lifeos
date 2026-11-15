'use client';

import {createContext,useCallback,useContext,useEffect,useRef,useState,ReactNode} from 'react';
import imagePool from '../lib/background-pool.json';

type BackgroundImage=typeof imagePool[number];
export const backgroundConfig={autoRotateMs:0,transitionMs:650};
const BackgroundContext=createContext<((mobile:boolean)=>BackgroundImage|undefined)|null>(null);
const storageKey='lifeos-background-last'; // Decorative preference only; no health data.

export function BackgroundProvider({children}:{children:ReactNode}){
 const last=useRef<string|null>(null);
 const pick=useCallback((mobile:boolean)=>{
  try{last.current=last.current||sessionStorage.getItem(storageKey)}catch{/* Storage can be disabled. */}
  const pool=imagePool.filter(image=>image.enabled&&(mobile||image.desktopEligible));
  const alternatives=pool.filter(image=>image.id!==last.current);
  const candidates=alternatives.length?alternatives:pool;
  const selected=candidates[Math.floor(Math.random()*candidates.length)];
  if(selected){last.current=selected.id;try{sessionStorage.setItem(storageKey,selected.id)}catch{/* Optional decorative persistence. */}}
  return selected;
 },[]);
 return <BackgroundContext.Provider value={pick}>{children}</BackgroundContext.Provider>;
}

export function BackgroundOverlay(){return <div className="background-overlay"/>}

type Frame={image:BackgroundImage;mobile:boolean;ready:boolean};
export function RandomBackground({pageKey,enabled=true,autoRotateMs=backgroundConfig.autoRotateMs}:{pageKey:string;enabled?:boolean;autoRotateMs?:number}){
 const pick=useContext(BackgroundContext);
 const [frames,setFrames]=useState<Frame[]>([]);
 const [reduce,setReduce]=useState(false);
 const retire=useRef<ReturnType<typeof setTimeout>|null>(null);
 useEffect(()=>{
  const preference=window.matchMedia('(prefers-reduced-motion: reduce)');
  const update=()=>setReduce(preference.matches);update();preference.addEventListener('change',update);
  return()=>preference.removeEventListener('change',update);
 },[]);
 const change=useCallback(()=>{
  if(!pick||document.hidden)return;
  const mobile=window.matchMedia('(max-width: 760px)').matches;
  const image=pick(mobile);
  if(image)setFrames(previous=>[...previous.filter(frame=>frame.ready&&frame.image.id!==image.id).slice(-1),{image,mobile,ready:false}]);
 },[pick]);
 useEffect(()=>{
  if(enabled)change();else setFrames([]);
  return()=>{if(retire.current)clearTimeout(retire.current)};
 },[pageKey,enabled,change]);
 useEffect(()=>{
  if(!enabled||autoRotateMs<=0||reduce)return;
  const timer=setInterval(change,Math.max(10000,autoRotateMs));
  return()=>clearInterval(timer);
 },[enabled,autoRotateMs,reduce,change]);
 function loaded(id:string){
  setFrames(previous=>previous.map(frame=>frame.image.id===id?{...frame,ready:true}:frame));
  if(retire.current)clearTimeout(retire.current);
  retire.current=setTimeout(()=>setFrames(previous=>previous.filter(frame=>frame.image.id===id)),reduce?0:backgroundConfig.transitionMs);
 }
 if(!enabled)return null;
 return <div className="random-background" aria-hidden="true" data-testid="random-background" data-page={pageKey} data-state={frames.at(-1)?.ready?'ready':'fallback'}>
  {frames.map(frame=>{const variant=frame.mobile?frame.image.mobile:frame.image.desktop;return <img key={frame.image.id} src={variant.src} width={variant.width} height={variant.height} alt="" decoding="async" loading="eager" fetchPriority="high" className={frame.ready?'background-photo ready':'background-photo'} data-background-id={frame.image.id} onLoad={()=>loaded(frame.image.id)} onError={()=>setFrames([])}/>})}
  <BackgroundOverlay/>
 </div>;
}
