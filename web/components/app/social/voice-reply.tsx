"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Loader2,Mic,RefreshCw,Send,X} from 'lucide-react';
import type {SocialCommandInput,SocialVoicePreview} from '@/lib/social-types';
import {useSocialTransport} from './transport';
export function VoiceReply({modelId,channel,text,disabled,prepare,onSend}:{modelId:string;channel:string;text:string;disabled:boolean;prepare:()=>SocialCommandInput|null;onSend:(preview:SocialVoicePreview,price:number)=>Promise<boolean>}){
 const {transport}=useSocialTransport();const dialog=useRef<HTMLDialogElement>(null);const requestId=useRef<string|null>(null);const requestBusy=useRef(false);
 const [open,setOpen]=useState(false);const [preview,setPreview]=useState<SocialVoicePreview|null>(null);const [loading,setLoading]=useState(false);const [sending,setSending]=useState(false);const [error,setError]=useState('');
 const [paid,setPaid]=useState(false);const [price,setPrice]=useState('');
 const load=useCallback(async(fresh=false)=>{
  if(requestBusy.current)return;const input=prepare();if(!input)return;
  requestBusy.current=true;setLoading(true);setError('');
  if(fresh || !requestId.current)requestId.current=crypto.randomUUID();
  const id=requestId.current;
  try{const result=await transport.socialVoicePreview(modelId,{id,contactKey:input.contactKey,...(fresh||!preview?{input,regenerate:fresh}:{})});
   if(result.error)setError(result.error);else if(result.preview){requestId.current=result.preview.id;setPreview(result.preview);}
  }catch{setError('Could not confirm this preview. Reopen it to check the same request.');}finally{requestBusy.current=false;setLoading(false);}
 },[modelId,prepare,preview,transport]);
 useEffect(()=>{if(open)dialog.current?.showModal();},[open]);
 useEffect(()=>{
  if(!open || !preview || !['queued','working'].includes(preview.status) || error)return;
  const timer=setInterval(()=>void load(),3000);return()=>clearInterval(timer);
 },[open,preview,load,error]);
 const processing=loading || Boolean(preview && ['queued','working'].includes(preview.status) && !error);
 const cents=paid&&/^\d+(?:[.,]\d{1,2})?$/.test(price.trim())?Math.round(Number(price.replace(',','.'))*100):0;
 const priceValid=!paid || cents>=300;
 async function send(){if(!preview || preview.status!=='ready' || sending || !priceValid)return;setSending(true);setError('');
  try{if(await onSend(preview,cents)){dialog.current?.close();setPreview(null);requestId.current=null;}else setError('Delivery request not confirmed. Close this window and check the conversation status before retrying.');}
  finally{setSending(false);}
 }
 return <>
  <button type="button" disabled={disabled||!text.trim()} title="Send as a voice note" aria-label="Prepare voice reply" onClick={()=>{setOpen(true);void load();}} className="app-btn app-btn-quiet h-9 w-9 shrink-0"><Mic className="h-4 w-4" /></button>
  {open&&createPortal(<dialog ref={dialog} onClose={()=>setOpen(false)} aria-labelledby="voice-reply-title" className="m-auto max-h-[85dvh] w-[calc(100%-24px)] max-w-md overflow-hidden rounded-xl border border-[var(--app-border-strong)] bg-[var(--app-surface)] p-0 text-[var(--app-text)] shadow-2xl backdrop:bg-black/75">
   <div className="flex max-h-[85dvh] flex-col"><div className="flex items-center gap-2 border-b border-[var(--app-border)] px-4 py-2"><Mic className="h-4 w-4" /><h2 id="voice-reply-title" className="flex-1 text-sm font-medium">Voice reply</h2><button type="button" aria-label="Close voice preview" onClick={()=>dialog.current?.close()} className="app-btn app-btn-quiet h-9 w-9"><X className="h-4 w-4" /></button></div>
   <div className="overflow-y-auto p-4 text-xs leading-5">
    {processing&&<p role="status" className="mb-3 flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />{preview?.status==='queued'?'Waiting for the worker…':'Preparing speech, voice and background…'}</p>}
    {error&&<p role="alert" className="mb-3 text-[#fca5a5]">{error}</p>}
    {preview?.status==='failed'&&<p role="alert" className="mb-3 text-[#fca5a5]">{preview.error}</p>}
    {preview?.playbackUrl&&<audio controls preload="metadata" src={preview.playbackUrl} className="my-3 w-full" onError={()=>setError('Could not play this preview. Use Reload audio to refresh its private link.')} />}
    <p className="mb-1 text-[10px] uppercase tracking-wide text-[var(--app-text-3)]">{preview?.spoken?'Spoken transcript':'Original reply'}</p><p className="whitespace-pre-wrap break-words">{preview?.spoken || text}</p>
    {preview?.ambience&&<p className="mt-3 text-[10px] text-[var(--app-text-3)]">Background · {preview.ambience}. Preview expires after 15 minutes.</p>}
    <p className="mt-3 text-[10px] text-[var(--app-text-3)]">Listen before sending. Preparing a preview does not send a message or mark the chat as seen.</p>
    {channel==='fanvue'&&<div className="mt-3 flex items-center gap-2"><button type="button" disabled={sending} onClick={()=>setPaid(false)} aria-pressed={!paid} className="app-btn app-btn-ghost min-h-9 px-3 text-xs">Free</button><button type="button" disabled={sending} onClick={()=>setPaid(true)} aria-pressed={paid} className="app-btn app-btn-ghost min-h-9 px-3 text-xs">Paid</button>{paid&&<label className="flex min-w-0 flex-1 items-center gap-1">$<input aria-label="Voice unlock price in USD" disabled={sending} inputMode="decimal" value={price} onChange={e=>setPrice(e.target.value)} placeholder="3.00 minimum" className="app-input min-w-0 text-xs!" /></label>}</div>}
   </div><div className="flex flex-wrap gap-2 border-t border-[var(--app-border)] p-3"><button type="button" disabled={processing||sending} onClick={()=>void load(true)} className="app-btn app-btn-quiet min-h-10 px-2 text-xs"><RefreshCw className="h-3.5 w-3.5" />Generate again</button>{preview?.status==='ready'&&<button type="button" disabled={loading||sending} onClick={()=>void load()} className="app-btn app-btn-quiet min-h-10 px-2 text-[10px]">Reload audio</button>}<button type="button" disabled={disabled||processing||sending||preview?.status!=='ready'||!priceValid||Boolean(error)} onClick={()=>void send()} className="app-btn app-btn-primary ml-auto min-h-10 px-3 text-xs">{sending?<Loader2 className="h-4 w-4 animate-spin" />:<Send className="h-3.5 w-3.5" />}Send voice{paid?` · $${(cents/100).toFixed(2)}`:''}</button></div></div>
  </dialog>,document.querySelector(".mini-shell, .app-scope") || document.body)}
 </>;
}
