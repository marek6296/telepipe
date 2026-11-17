import assert from 'node:assert/strict';
import { selectSocialMedia } from '../lib/social-media-policy.ts';
const model='10000000-0000-0000-0000-000000000001';
const media='20000000-0000-4000-8000-000000000001';
const scope={modelId:model,channel:'telegram' as const,externalId:'123',accountScope:'telegram:one',messageIds:['42']};
const row={id:media,model_id:model,channel:'telegram',external_id:'123',account_scope:'telegram:one',message_id:42,kind:'video',mime_type:'video/mp4',storage_path:`${model}/telegram/42/${media}.mp4`,status:'ready',transcript:'hello',description:'waves at the camera',duration_seconds:12,source_url:'https://provider/private?token=secret'};
const picked=selectSocialMedia([row],scope);
assert.equal(picked.length,1);
assert.equal(picked[0].media.transcript,'hello');
assert.equal(picked[0].media.description,'waves at the camera');
assert.equal(picked[0].media.playbackUrl,null);
assert.equal(JSON.stringify(picked).includes('secret'),false);
for(const patch of [{model_id:'foreign'},{external_id:'other'},{channel:'instagram'},{account_scope:'old-account'},{message_id:99},{id:'not-an-id'}])
  assert.equal(selectSocialMedia([{...row,...patch}],scope).length,0,'foreign or invalid media must never be signed');
for(const path of [`other/telegram/file.mp4`,`${model}/telegram/../secret`,`${model}/telegram/%2e%2e/secret`,'https://evil.example/file.mp4'])
  assert.equal(selectSocialMedia([{...row,storage_path:path}],scope)[0].storagePath,null);
const failed=selectSocialMedia([{...row,status:'failed',error:'provider secret=token raw stack'}],scope)[0];
assert.equal(failed.media.error,'Media could not be processed.');
assert.equal(failed.storagePath,row.storage_path,'a playable file survives analysis failure');
assert.equal(selectSocialMedia([{...row,duration_seconds:-10}],scope)[0].media.durationSeconds,null);
console.log('PASS Social media ownership, storage paths, safe DTOs and partial analysis');
