"use client";

import {useCallback,useEffect,useRef,useState} from 'react';
import {FileUser,Loader2,RefreshCw,X} from 'lucide-react';
import {useSocialTransport} from './transport';
import type {SocialBrief,SocialContact} from '@/lib/social-types';
import {CHANNEL_NAMES} from './state';

export function PersonBrief({modelId,contact}:{modelId:string;contact:SocialContact}) {
  const {transport}=useSocialTransport();
  const dialog=useRef<HTMLDialogElement>(null);
  const busy=useRef(false);
  const [open,setOpen]=useState(false);
  const [loading,setLoading]=useState(false);
  const [brief,setBrief]=useState<SocialBrief|null>(null);
  const [error,setError]=useState('');
  const trigger=useRef<HTMLButtonElement>(null);
  const load=useCallback(async(refresh=false)=>{
    if(busy.current)return;
    busy.current=true;setLoading(true);setError('');
    try {
      const result=await transport.getSocialPersonBrief(modelId,contact.key,refresh);
      if(result.error)setError(result.error);
      else if(result.brief)setBrief(result.brief);
    } catch {setError('Could not load the summary. Try again.');}
    finally {busy.current=false;setLoading(false);}
  },[transport,modelId,contact.key]);
  useEffect(()=>{
    if(!open || !brief?.generating)return;
    const timer=setInterval(()=>void load(),4000);
    return ()=>clearInterval(timer);
    // Recheck an already-running generation; cached opens never start another one.
  },[open,brief?.generating,load]);
  function close(){dialog.current?.close();}
  return <>
    <button ref={trigger} type="button" onClick={()=>{setOpen(true);dialog.current?.showModal();void load();}} aria-label="Person summary" title="Person summary" className="app-btn app-btn-quiet h-8 w-8"><FileUser className="h-4 w-4" /></button>
    <dialog ref={dialog} onClose={()=>{setOpen(false);trigger.current?.focus();}} onClick={event=>{if(event.target===event.currentTarget)close();}}
      aria-labelledby="person-brief-title" className="m-auto max-h-[85dvh] w-[calc(100%-24px)] max-w-lg overflow-hidden rounded-2xl border border-[var(--app-border-strong)] bg-[var(--app-surface)] p-0 text-[var(--app-text)] shadow-2xl backdrop:bg-black/70">
      <div className="flex max-h-[85dvh] flex-col">
        <div className="flex shrink-0 items-center gap-2 border-b border-[var(--app-border)] px-4 py-3">
          <FileUser className="h-4 w-4 shrink-0" /><h2 id="person-brief-title" className="min-w-0 flex-1 truncate text-sm font-medium">Person summary</h2>
          <button type="button" onClick={close} aria-label="Close summary" className="app-btn app-btn-quiet h-9 w-9"><X className="h-4 w-4" /></button>
        </div>
        <div className="overflow-y-auto overscroll-contain px-4 py-3 text-xs leading-5">
          <p className="mb-1 font-medium">{contact.displayName || contact.username}</p>
          {brief && <p className="mb-3 text-[11px] text-[var(--app-text-3)]">{brief.accounts.map(a=>`${CHANNEL_NAMES[a.channel]} ${a.name}`).join(' · ')}</p>}
          {(loading || brief?.generating) && <p role="status" className="mb-3 flex items-center gap-2 text-[var(--app-text-3)]"><Loader2 className="h-4 w-4 animate-spin" />{brief?.summary?'Updating summary…':'Preparing summary from linked chats…'}</p>}
          {error && <p role="alert" className="mb-3 text-[#fca5a5]">{error}</p>}
          {brief?.summary && <><p className="whitespace-pre-wrap break-words">{brief.summary}</p><p className="mt-4 text-[10px] text-[var(--app-text-3)]">Saved {brief.generatedAt ? new Date(brief.generatedAt).toLocaleString():''} · AI summary; check the chat for exact wording.</p><details className="mt-2 text-[10px] text-[var(--app-text-3)]"><summary className="cursor-pointer">History included{brief.truncated?' · excerpts':''}</summary><p className="mt-1 whitespace-pre-wrap">{brief.coverage}</p></details></>}
        </div>
        <div className="flex shrink-0 justify-end border-t border-[var(--app-border)] px-4 py-2"><button type="button" disabled={loading || (brief?.generating && !error)} onClick={()=>void load(true)} className="app-btn app-btn-ghost min-h-10 px-3 text-xs"><RefreshCw className="h-3.5 w-3.5" />{brief?.summary?'Refresh summary':'Try again'}</button></div>
      </div>
    </dialog>
  </>;
}
