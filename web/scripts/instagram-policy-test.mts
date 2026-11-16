import assert from 'node:assert/strict';
import { validateInstagramPatch } from '../lib/instagram-policy.ts';
assert.equal(validateInstagramPatch({bio_link:'https://linkovne.com/simona'}).error, undefined);
for (const url of ['http://linkovne.com/simona','https://linkovne.com.evil.test/a','https://u:p@linkovne.com/a','https://fanvue.com/a','https://linkovne.com/','https://linkovne.com:44/a']) {
  assert.ok(validateInstagramPatch({bio_link:url}).error, url);
}
assert.ok(validateInstagramPatch({access_token:'secret'}).error);
assert.ok(validateInstagramPatch({reply_comments:'false'}).error);
assert.ok(validateInstagramPatch({reply_mode:'hot'}).error);
assert.deepEqual(validateInstagramPatch({telegram_handle:'@simona_here',sync_enabled:true}).update, {telegram_handle:'simona_here',sync_enabled:true});
assert.deepEqual(validateInstagramPatch({funnel_target:'both'}).update,{funnel_target:'both'});
console.log('PASS: actual Instagram setting validator, URL origins, booleans and protected columns');
