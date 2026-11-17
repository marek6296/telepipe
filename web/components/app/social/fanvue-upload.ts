import type {SocialTransport} from './transport-core';
import type {FanvueMediaItem} from '@/lib/social-types';
import {uploadFile,type MediaJob} from '@/lib/fanvue-owner-policy';
export async function runMediaJob(transport:SocialTransport,modelId:string,scope:string,input:Omit<MediaJob,'id'> & Record<string,unknown>,signal?:AbortSignal):Promise<Record<string,unknown>>{
 const request={...input,id:crypto.randomUUID()};
 const started=Date.now();
 while(Date.now()-started<150000){
  signal?.throwIfAborted();
  const result=await transport.fanvueOwnerMedia(modelId,scope,request);
  if(result.error)throw Error(result.error);
  if(result.job?.status==='done')return result.job.output;
  if(result.job?.status==='failed')throw Error(result.job.error || 'Fanvue could not process this request.');
  await new Promise<void>((resolve,reject)=>{const timer=setTimeout(done,1000);function done(){signal?.removeEventListener('abort',abort);resolve();}function abort(){clearTimeout(timer);reject(new DOMException('Cancelled','AbortError'));}signal?.addEventListener('abort',abort,{once:true});});
 }
 throw Error('The worker is taking too long. Check Worker online and try again. No message was sent.');
}
function putPart(url:string,bytes:Blob,signal:AbortSignal,onProgress:(bytes:number)=>void):Promise<string>{
 return new Promise((resolve,reject)=>{
  const xhr=new XMLHttpRequest();xhr.open('PUT',url);xhr.timeout=180000;
  const abort=()=>xhr.abort();signal.addEventListener('abort',abort,{once:true});
  const clean=()=>signal.removeEventListener('abort',abort);
  xhr.upload.onprogress=e=>onProgress(e.loaded);
  xhr.onload=()=>{clean();if(xhr.status<200||xhr.status>=300)return reject(Error('Upload part failed. Retry the file.'));
   const etag=xhr.getResponseHeader('ETag');if(!etag)return reject(Error('Fanvue did not return an upload receipt. Try another browser or file.'));resolve(etag);};
  xhr.onerror=()=>{clean();reject(Error('Upload connection failed. Keep the app open and retry.'));};
  xhr.ontimeout=()=>{clean();reject(Error('Upload timed out. Retry on a stable connection.'));};
  xhr.onabort=()=>{clean();reject(new DOMException('Cancelled','AbortError'));};xhr.send(bytes);
 });
}
export async function uploadFanvueFile(transport:SocialTransport,modelId:string,scope:string,file:File,signal:AbortSignal,onProgress:(percent:number,label:string)=>void):Promise<FanvueMediaItem>{
 const type=file.type || (/\.mov$/i.test(file.name)?'video/quicktime':/\.heic$/i.test(file.name)?'image/heic':'');
 const info=uploadFile({name:file.name,size:file.size,type});
 const uploadKey=crypto.randomUUID();
 // Keep the init request ID so later parts can only use this owner's persisted upload.
 async function init(){
  const start=Date.now();const request={id:uploadKey,action:'init',file:info};
  while(Date.now()-start<150000){signal.throwIfAborted();const r=await transport.fanvueOwnerMedia(modelId,scope,request);if(r.error)throw Error(r.error);if(r.job?.status==='failed')throw Error(r.job.error);if(r.job?.status==='done')return r.job.output;await new Promise(r=>setTimeout(r,1000));}
  throw Error('The worker did not start the upload. Try again.');
 }
 onProgress(0,'Preparing upload');const session=await init();const partSize=Number(session.partSize);const count=Math.ceil(file.size/partSize);
 if(!Number.isFinite(partSize)||partSize<=0||count>256)throw Error('Fanvue returned an invalid upload session.');
 const parts:{PartNumber:number;ETag:string}[]=[];let completed=0;
 for(let from=1;from<=count;from+=8){
  const output=await runMediaJob(transport,modelId,scope,{action:'part',uploadKey,from,to:Math.min(count,from+7)},signal);
  for(const part of output.parts as {partNumber:number;url:string}[]){
   signal.throwIfAborted();const chunk=file.slice((part.partNumber-1)*partSize,Math.min(file.size,part.partNumber*partSize));
   let etag='';
   for(let attempt=0;attempt<3;attempt++){
    try {
     if(attempt>0){const renewed=await runMediaJob(transport,modelId,scope,{action:'part',uploadKey,from:part.partNumber,to:part.partNumber},signal);part.url=(renewed.parts as {url:string}[])[0].url;}
     etag=await putPart(part.url,chunk,signal,n=>onProgress(Math.round((completed+n)*100/file.size),'Uploading'));break;}
    catch(error){signal.throwIfAborted();if(attempt===2)throw error;}
   }
   parts.push({PartNumber:part.partNumber,ETag:etag});completed+=chunk.size;onProgress(Math.round(completed*100/file.size),'Uploading');
  }
 }
 await runMediaJob(transport,modelId,scope,{action:'complete',uploadKey,parts},signal);
 onProgress(100,'Fanvue is processing this file');
 const until=Date.now()+15*60*1000;
 while(Date.now()<until){
  const output=await runMediaJob(transport,modelId,scope,{action:'status',uploadKey},signal);const item=output.item as FanvueMediaItem;
  if(item?.status==='ready')return {...item,name:item.name || file.name};
  if(item?.status==='error')throw Error('Fanvue could not process this file. Check it in Fanvue Vault.');
  await new Promise(r=>setTimeout(r,4000));
 }
 throw Error('Fanvue is still processing the file. You can select it from Vault once it is ready.');
}
