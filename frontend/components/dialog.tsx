'use client';
import {ReactNode,useEffect,useRef} from 'react';
import {X} from 'lucide-react';
export function Dialog({title,onClose,children}:{title:string;onClose:()=>void;children:ReactNode}){
 const ref=useRef<HTMLDialogElement>(null);
 useEffect(()=>{const node=ref.current;node?.showModal();return()=>node?.close()},[]);
 return <dialog className="lifeos-dialog" ref={ref} aria-label={title} onCancel={e=>{e.preventDefault();onClose()}} onClick={e=>{if(e.target===e.currentTarget)onClose()}}><div className="dialog-head"><h2>{title}</h2><button className="icon" aria-label="关闭弹窗" onClick={onClose}><X/></button></div>{children}</dialog>
}
