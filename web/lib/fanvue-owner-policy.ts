const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const MAX_FILE_BYTES=1610612736;
export function mediaBundle(ids:unknown,price:unknown){
 if(!Array.isArray(ids)||ids.length<1||ids.length>20||ids.some(id=>typeof id!=='string'||!UUID.test(id))||new Set(ids).size!==ids.length)throw Error('Select 1–20 different photos, videos or audio.');
 if(!Number.isInteger(price)||Number(price)<0||(Number(price)>0&&Number(price)<300)||Number(price)>2147483647)throw Error('Use Free or an unlock price of at least $3.00.');
 return {mediaUuids:[...ids] as string[],priceCents:Number(price)};
}
export function uploadFile(v:{name?:unknown;size?:unknown;type?:unknown}){
 if(typeof v.name!=='string'||!v.name.trim()||v.name.length>200||/[\x00-\x1f/\\]/.test(v.name))throw Error('Invalid filename.');
 if(!Number.isInteger(v.size)||Number(v.size)<=0||Number(v.size)>MAX_FILE_BYTES)throw Error('Each file must be under 1.5 GiB.');
 const type=typeof v.type==='string'?v.type:'';
 if(!/^(image\/(jpeg|png|webp|heic|heif)|video\/(mp4|quicktime|webm|x-m4v)|audio\/(mpeg|mp3|mp4|x-m4a|aac|wav|x-wav|ogg|webm))$/.test(type))throw Error('Choose a supported photo, video or audio (JPEG, PNG, WebP, HEIC, MP4, MOV or WebM).');
 return {name:v.name,size:Number(v.size),type,mediaType:type.startsWith('image/')?'image':type.startsWith('video/')?'video':'audio'};
}
export type MediaJob={id:string;action:'list'|'init'|'part'|'complete'|'status';page?:number;folder?:string;file?:ReturnType<typeof uploadFile>;uploadKey?:string;from?:number;to?:number;parts?:{PartNumber:number;ETag:string}[]};
export function mediaJob(value:unknown):MediaJob {
 const v=value as Record<string,unknown>;
 if(!v||typeof v.id!=='string'||!UUID.test(v.id))throw Error('Invalid media request.');
 if(v.action==='list'){
  const page=v.page??1;if(!Number.isInteger(page)||Number(page)<1||Number(page)>10000||typeof(v.folder??'')!=='string'||String(v.folder??'').length>200)throw Error('Invalid Vault page.');
  return {id:v.id,action:'list',page:Number(page),folder:String(v.folder??'')};
 }
 if(v.action==='init')return {id:v.id,action:'init',file:uploadFile(v.file as Parameters<typeof uploadFile>[0])};
 if(typeof v.uploadKey!=='string'||!UUID.test(v.uploadKey))throw Error('Invalid upload session.');
 const base={id:v.id,uploadKey:v.uploadKey};
 if(v.action==='status')return {...base,action:'status'};
 if(v.action==='part'){
  if(!Number.isInteger(v.from)||!Number.isInteger(v.to)||Number(v.from)<1||Number(v.to)>256||Number(v.to)<Number(v.from)||Number(v.to)-Number(v.from)>7)throw Error('Invalid upload parts.');
  return {...base,action:'part',from:Number(v.from),to:Number(v.to)};
 }
 if(v.action==='complete'){
  if(!Array.isArray(v.parts)||!v.parts.length||v.parts.length>256)throw Error('Upload has no completed parts.');
  const parts=v.parts.map((p:Record<string,unknown>)=>{if(!Number.isInteger(p.PartNumber)||Number(p.PartNumber)<1||Number(p.PartNumber)>256||typeof p.ETag!=='string'||!/^"?[a-f0-9]{32}(?:-\d+)?"?$/i.test(p.ETag))throw Error('Invalid upload receipt.');return {PartNumber:Number(p.PartNumber),ETag:p.ETag};});
  return {...base,action:'complete',parts};
 }
 throw Error('Unknown media action.');
}
