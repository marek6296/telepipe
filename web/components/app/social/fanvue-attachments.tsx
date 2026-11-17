"use client";
import {useEffect,useRef,useState} from 'react';
import {createPortal} from "react-dom";
import Image from 'next/image';
import {Check,FolderOpen,ImagePlus,Loader2,Paperclip,Send,Upload,X} from 'lucide-react';
import {useSocialTransport} from './transport';
import {runMediaJob,uploadFanvueFile} from './fanvue-upload';
import {mediaBundle} from '@/lib/fanvue-owner-policy';
import type {FanvueMediaItem,SocialContact} from '@/lib/social-types';
export function FanvueAttachments({modelId,contact,disabled,initialCaption,onSend}:{modelId:string;contact:SocialContact;disabled:boolean;initialCaption:string;onSend:(media:string[],price:number,caption:string)=>Promise<boolean>}){
 const {transport}=useSocialTransport();const modal=useRef<HTMLDialogElement>(null);const input=useRef<HTMLInputElement>(null);
 const controller=useRef<AbortController|null>(null);const listing=useRef<AbortController|null>(null);
 const [open,setOpen]=useState(false);
 useEffect(()=>{if(open)modal.current?.showModal();},[open]);
 const [items,setItems]=useState<FanvueMediaItem[]>([]);const [selected,setSelected]=useState<FanvueMediaItem[]>([]);
 const [folders,setFolders]=useState<string[]>([]);const [folder,setFolder]=useState('');const [search,setSearch]=useState('');const [page,setPage]=useState(1);const [more,setMore]=useState(false);
 const [loading,setLoading]=useState(false);const [uploading,setUploading]=useState(false);const [sending,setSending]=useState(false);
 const [progress,setProgress]=useState('');const [error,setError]=useState('');const [caption,setCaption]=useState('');
 const [paid,setPaid]=useState<boolean|null>(null);const [price,setPrice]=useState('');
 useEffect(()=>()=>{controller.current?.abort();listing.current?.abort();},[]);
 async function load(next=1,nextFolder=folder){
  listing.current?.abort();const c=new AbortController();listing.current=c;setLoading(true);setError('');
  try{const r=await runMediaJob(transport,modelId,contact.accountScope,{action:'list',page:next,folder:nextFolder},c.signal);
   if(c.signal.aborted)return;setItems(previous=>next===1?r.items as FanvueMediaItem[]:[...previous,...(r.items as FanvueMediaItem[]).filter(i=>!previous.some(p=>p.uuid===i.uuid))]);setFolders(r.folders as string[]);setPage(next);setMore(r.hasMore===true);
  }catch(e){if(!c.signal.aborted)setError(e instanceof Error?e.message:'Could not load Vault.');}finally{if(!c.signal.aborted)setLoading(false);}
 }
 function toggle(item:FanvueMediaItem){setSelected(previous=>previous.some(p=>p.uuid===item.uuid)?previous.filter(p=>p.uuid!==item.uuid):previous.length<20?[...previous,item]:previous);}
 async function upload(files:FileList|null){
  if(!files?.length)return;
  if(files.length+selected.length>20){setError('Select at most 20 photos, videos or audio in one message.');return;}
  const c=new AbortController();controller.current=c;setUploading(true);setError('');
  try{for(const file of Array.from(files)){
   const item=await uploadFanvueFile(transport,modelId,contact.accountScope,file,c.signal,(percent,state)=>setProgress(`${file.name} · ${state}${state==='Uploading'?` ${percent}%`:''}`));
   setSelected(previous=>previous.some(p=>p.uuid===item.uuid)?previous:[...previous,item]);
  }setProgress('Uploads ready');}
  catch(e){if(!c.signal.aborted)setError(e instanceof Error?e.message:'Upload failed.');else setError('Upload cancelled. Already completed files remain selected.');}
  finally{setUploading(false);if(input.current)input.current.value='';}
 }
 let cents=0;let priceError='';
 if(paid){if(!/^\d+(?:[.,]\d{1,2})?$/.test(price.trim()))priceError='Enter the total unlock price.';else cents=Math.round(Number(price.replace(',','.'))*100);if(!priceError && cents<300)priceError='Minimum unlock price is $3.00.';}
 async function send(){
  setError('');if(paid===null){setError('Choose Free or Paid before sending.');return;}if(priceError){setError(priceError);return;}
  try{const bundle=mediaBundle(selected.map(i=>i.uuid),cents);setSending(true);
   if(await onSend(bundle.mediaUuids,bundle.priceCents,caption.trim())){setSelected([]);setPaid(null);setPrice('');modal.current?.close();}
   else setError('Could not queue this message. Check the conversation status; the selected media is kept.');
  }catch(e){setError(e instanceof Error?e.message:'Could not queue media.');}finally{setSending(false);}
 }
 const busy=uploading||sending;
 return <>
  <button type="button" aria-label="Attach Fanvue photos, videos or audio" title="Attach photos, videos or audio" disabled={disabled} onClick={()=>{setCaption(initialCaption);setOpen(true);void load();}} className="app-btn app-btn-quiet h-9 gap-1.5 px-2">{uploading?<Loader2 className="h-4 w-4 animate-spin" />:<Paperclip className="h-4 w-4" />}{selected.length>0&&<span className="text-[10px]">{selected.length}</span>}</button>
  {open&&createPortal(<dialog ref={modal} onClose={()=>setOpen(false)} aria-labelledby="fanvue-media-title" className="m-auto max-h-[92dvh] w-[calc(100%-16px)] max-w-xl overflow-hidden rounded-xl border border-[var(--app-border-strong)] bg-[var(--app-surface)] p-0 text-[var(--app-text)] shadow-2xl backdrop:bg-black/75">
   <div className="flex max-h-[92dvh] flex-col">
    <div className="flex shrink-0 items-center gap-2 border-b border-[var(--app-border)] px-3 py-2"><ImagePlus className="h-4 w-4" /><h2 id="fanvue-media-title" className="flex-1 text-sm font-medium">Media &amp; voice notes</h2><button type="button" aria-label="Close media picker" className="app-btn app-btn-quiet h-9 w-9" onClick={()=>modal.current?.close()}><X className="h-4 w-4" /></button></div>
    <div className="min-h-0 overflow-y-auto overscroll-contain p-3 text-xs">
     <p className="mb-3 text-[var(--app-text-3)]">To {contact.username?`@${contact.username}`:contact.displayName} · Fanvue</p>
     <input ref={input} type="file" multiple accept="image/jpeg,image/png,image/webp,image/heic,image/heif,video/mp4,video/quicktime,video/webm,video/x-m4v,audio/mpeg,audio/mp4,audio/aac,audio/wav,audio/ogg,audio/webm" className="sr-only" onChange={e=>void upload(e.target.files)} />
     <div className="flex items-center gap-2"><button type="button" disabled={busy} className="app-btn app-btn-ghost min-h-10 px-3 text-xs" onClick={()=>input.current?.click()}><Upload className="h-4 w-4" />From device</button><span className="text-[10px] text-[var(--app-text-3)]">Up to 20 files · 1.5 GiB each</span></div>
     {uploading&&<div role="status" className="my-3 flex items-center gap-2"><Loader2 className="h-4 w-4 shrink-0 animate-spin" /><p className="min-w-0 flex-1 break-words text-[11px]">{progress}</p><button type="button" onClick={()=>controller.current?.abort()} className="underline">Cancel</button></div>}
     {uploading&&<p className="mb-2 text-[10px] text-[var(--app-text-3)]">Keep this chat open until uploading and Fanvue processing finish.</p>}
     {error&&<p role="alert" className="my-2 break-words text-[11px] text-[#fca5a5]">{error}</p>}
     {selected.length>0&&<div className="my-3"><p className="mb-2 font-medium">Selected · {selected.length}/20</p><div className="flex gap-2 overflow-x-auto pb-1">{selected.map((item,index)=><button type="button" key={item.uuid} disabled={sending} onClick={()=>toggle(item)} className="relative flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-[#40d86c]" aria-label={`Remove ${item.name || `media ${index+1}`}`}>{item.thumb?<Image src={item.thumb} alt="Selected media" fill sizes="64px" unoptimized className="object-cover" />:<ImagePlus className="h-5 w-5" />}<span className="absolute right-0 top-0 rounded-bl bg-black/80 p-1"><X className="h-3 w-3" /></span><span className="absolute bottom-0 left-0 bg-black/80 px-1 text-[9px]">{index+1} · {item.kind}</span></button>)}</div></div>}
     <div className="mb-2 mt-4 flex items-center justify-between"><h3 className="flex items-center gap-1.5 font-medium"><FolderOpen className="h-3.5 w-3.5" />Fanvue Vault</h3><button type="button" disabled={loading} onClick={()=>void load()} className="text-[10px] underline">Refresh</button></div>
     <div className="mb-2 flex gap-2"><select aria-label="Vault folder" className="app-input min-w-0 flex-1 text-xs!" value={folder} onChange={e=>{setFolder(e.target.value);void load(1,e.target.value);}}><option value="">All folders</option>{folders.map(f=><option key={f}>{f}</option>)}</select><input aria-label="Search loaded Vault media" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search…" className="app-input min-w-0 flex-1 text-xs!" /></div>
     <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">{items.filter(i=>i.name.toLowerCase().includes(search.toLowerCase())).map(item=><button type="button" key={item.uuid} disabled={busy || (selected.length>=20&&!selected.some(s=>s.uuid===item.uuid))} aria-label={`Select ${item.name || item.kind}`} aria-pressed={selected.some(s=>s.uuid===item.uuid)} onClick={()=>toggle(item)} className="relative aspect-square overflow-hidden rounded-lg border border-[var(--app-border)] bg-black/40">{item.thumb?<Image src={item.thumb} alt={item.name || item.kind} fill sizes="150px" unoptimized className="object-cover" />:<span className="text-[10px]">{item.kind}</span>}{selected.some(s=>s.uuid===item.uuid)&&<span className="absolute right-1 top-1 rounded-full bg-[#40d86c] p-1 text-black"><Check className="h-3 w-3" /></span>}<span className="absolute inset-x-0 bottom-0 truncate bg-black/75 px-1 py-1 text-[9px]">{item.kind==='video'?'▶ ':item.kind==='audio'?'♫ ':''}{item.name || item.kind}</span></button>)}</div>
     {loading&&<p role="status" className="my-3 flex items-center gap-2 text-[11px]"><Loader2 className="h-3.5 w-3.5 animate-spin" />Loading Vault…</p>}
     {!loading&&!items.length&&<p className="my-3 text-[11px] text-[var(--app-text-3)]">No photos, videos or audio in this folder.</p>}
     {more&&<button type="button" disabled={loading} className="app-btn app-btn-quiet mx-auto mt-2 min-h-9 px-3 text-xs" onClick={()=>void load(page+1)}>Load more</button>}
    </div>
    <div className="shrink-0 space-y-2 border-t border-[var(--app-border)] p-3">
     <textarea aria-label="Media message caption" disabled={sending} maxLength={4000} rows={2} value={caption} onChange={e=>setCaption(e.target.value)} placeholder="Message (optional)…" className="app-input resize-none text-xs!" />
     <div className="flex items-center gap-2"><button type="button" disabled={sending} aria-pressed={paid===false} onClick={()=>setPaid(false)} className={`app-btn min-h-9 px-3 text-xs ${paid===false?'app-btn-primary':'app-btn-ghost'}`}>Free</button><button type="button" disabled={sending} aria-pressed={paid===true} onClick={()=>setPaid(true)} className={`app-btn min-h-9 px-3 text-xs ${paid===true?'app-btn-primary':'app-btn-ghost'}`}>Paid</button>{paid&&<label className="flex min-w-0 flex-1 items-center gap-1.5 text-xs">$<input aria-label="Total unlock price in USD" disabled={sending} inputMode="decimal" value={price} onChange={e=>setPrice(e.target.value)} placeholder="3.00 minimum" className="app-input min-w-0 text-xs!" /></label>}</div>
     <button type="button" disabled={disabled||busy||!selected.length||paid===null||Boolean(priceError)} onClick={()=>void send()} className="app-btn app-btn-primary min-h-10 w-full justify-center text-xs">{sending?<Loader2 className="h-4 w-4 animate-spin" />:<Send className="h-4 w-4" />}Send {selected.length} {selected.length===1?'item':'items'}{paid===false?' · Free':paid===true&&!priceError?` · $${(cents/100).toFixed(2)} total`:''}</button>
    </div>
   </div>
  </dialog>,document.querySelector(".mini-shell, .app-scope") || document.body)}
 </>;
}
