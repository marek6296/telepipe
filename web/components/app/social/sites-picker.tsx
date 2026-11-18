"use client";

import {useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Globe,Loader2,Send,X} from 'lucide-react';
import type {SocialSite} from '@/lib/social-types';

export function SitesPicker({sites,disabled,onSend}:{sites:SocialSite[];disabled:boolean;onSend:(site:SocialSite)=>Promise<boolean>}){
  const dialog=useRef<HTMLDialogElement>(null);
  const busy=useRef(false);
  const title=useId();
  const [open,setOpen]=useState(false);
  const [sending,setSending]=useState<string|null>(null);
  useEffect(()=>{if(open)dialog.current?.showModal();},[open]);
  async function send(site:SocialSite){
    if(busy.current || disabled || !site.available)return;
    busy.current=true;setSending(site.url);
    try{await onSend(site);dialog.current?.close();}
    finally{busy.current=false;setSending(null);}
  }
  return <>
    <button type="button" disabled={disabled} onClick={event=>{event.preventDefault();setOpen(true);}} className="social-sites-trigger app-btn app-btn-quiet min-h-7 gap-1 px-1.5 text-[10px]" aria-label="Sites"><Globe className="h-3.5 w-3.5"/>Sites</button>
    {open&&createPortal(<dialog ref={dialog} onClose={()=>setOpen(false)} onClick={event=>{if(event.target===event.currentTarget)dialog.current?.close();}} aria-labelledby={title} className="m-auto max-h-[85dvh] w-[calc(100%-24px)] max-w-sm overflow-hidden rounded-xl border border-[var(--app-border-strong)] bg-[var(--app-surface)] p-0 text-[var(--app-text)] shadow-2xl backdrop:bg-black/75">
      <div className="flex items-center gap-2 border-b border-[var(--app-border)] px-4 py-2"><Globe className="h-4 w-4"/><h2 id={title} className="flex-1 text-sm font-medium">Sites</h2><button type="button" aria-label="Close sites" onClick={()=>dialog.current?.close()} className="app-btn app-btn-quiet h-9 w-9"><X className="h-4 w-4"/></button></div>
      <div className="max-h-[65dvh] space-y-2 overflow-y-auto p-3">
        <p className="mb-3 text-[11px] text-[var(--app-text-3)]">Choose a link to send to this conversation.</p>
        {sites.length===0&&<p className="py-3 text-xs text-[var(--app-text-3)]">No site links configured for this model yet.</p>}
        {sites.map(site=><button key={site.url} type="button" disabled={disabled || Boolean(sending) || !site.available} onClick={()=>void send(site)} aria-label={`Send ${site.label} link`} className="flex min-h-14 w-full items-center gap-3 rounded-lg border border-[var(--app-border)] bg-[var(--app-bg)] px-3 py-2 text-left disabled:opacity-45"><span className="min-w-0 flex-1"><span className="block text-xs font-medium">{site.label}</span><span className="block break-all text-[10px] leading-4 text-[var(--app-text-3)]">{site.url}</span>{site.reason&&<span className="mt-1 block text-[10px] text-[var(--app-text-3)]">{site.reason}</span>}</span>{sending===site.url?<Loader2 className="h-4 w-4 shrink-0 animate-spin"/>:<Send className="h-4 w-4 shrink-0"/>}</button>)}
      </div>
    </dialog>,document.querySelector('.mini-shell, .app-scope')||document.body)}
  </>;
}
