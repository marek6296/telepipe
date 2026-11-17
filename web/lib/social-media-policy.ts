import type { SocialChannel, SocialMedia } from './social-types';

type Row = Record<string, unknown>;
export type MediaScope = {modelId:string;channel:SocialChannel;externalId:string;accountScope:string;messageIds:string[]};
export type AuthorizedMedia = {messageId:string;storagePath:string|null;originalContent:string|null;media:SocialMedia};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const text=(value:unknown,max=16000)=>typeof value==='string' ? value.slice(0,max) : '';
const kinds=['audio','video','image','file'];
const states=['pending','processing','ready','unavailable','failed'];
const errors:Record<string,string>={
  too_large:'This attachment is too large to process.',
  file_too_large:'This attachment exceeds the 40 MB processing limit.',
  duration_limit:'Audio and video must have a known duration of up to 3 minutes.',
  dimensions_limit:'This attachment exceeds the supported image dimensions.',
  history_limit:'This older attachment is outside the media recovery window.',
  incomplete_media:'The complete attachment could not be converted.',
  invalid_media:'This file could not be decoded.',
  empty_media:'The attachment contains no data.',
  unsupported_media:'This attachment format is not supported.',
  transcription_unavailable:'The file is available, but its transcript could not be completed.',
  description_unavailable:'The file is available, but its visual description could not be completed.',
  processing_failed:'Media processing failed. It will be retried when possible.',
  source_unavailable:'The original attachment is no longer available.',
  download_failed:'The attachment could not be downloaded.',
  unsupported_type:'This attachment format is not supported.',
  analysis_failed:'The file is available, but its analysis could not be completed.',
  no_speech:'No speech was detected.',
  timeout:'Processing took too long. This attachment may be unavailable.',
};

/** Defense in depth: no provider URL, credential or foreign path enters a DTO. */
export function selectSocialMedia(rows:Row[],scope:MediaScope):AuthorizedMedia[] {
  const wanted=new Set(scope.messageIds);
  return rows.flatMap(row=>{
    const id=text(row.id,80), messageId=String(row.message_id ?? '');
    if(!uuid.test(id) || row.model_id!==scope.modelId || row.channel!==scope.channel
      || String(row.external_id)!==scope.externalId || row.account_scope!==scope.accountScope || !wanted.has(messageId)) return [];
    const kind=text(row.kind), state=text(row.status), path=text(row.storage_path,1000);
    const validPath=path.startsWith(`${scope.modelId}/${scope.channel}/`) && /^[a-zA-Z0-9_/.\-]+$/.test(path)
      && !path.split('/').some(part=>!part || part==='.' || part==='..');
    const duration=Number(row.duration_seconds);
    return [{messageId,storagePath:validPath ? path : null,originalContent:typeof row.original_content==='string' ? row.original_content : null,media:{
      id,kind:(kinds.includes(kind) ? kind : 'file') as SocialMedia['kind'],playbackUrl:null,
      mimeType:text(row.mime_type,120)||null,transcript:text(row.transcript)||null,description:text(row.description)||null,
      status:(states.includes(state) ? state : 'unavailable') as SocialMedia['status'],
      error:row.error ? errors[text(row.error,100)] || 'Media could not be processed.' : null,
      durationSeconds:row.duration_seconds!=null && Number.isFinite(duration) && duration>=0 ? duration : null,
    }}];
  });
}
