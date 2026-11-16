import assert from "node:assert/strict";
import {
  authorizeSocialOwner, parseContactKey, parseSocialQuery, validateSocialCommand,
  mapSocialContact, mapSocialMessage, groupSocialPeople,
} from "../lib/social-policy.ts";

const modelId = "c694da7e-e200-46d5-9b43-aa1a7863162f";
const ownerId = "0efff75b-734d-42c4-b679-99c0845f7636";
const requestId = "01ea640c-006b-4a90-a7cb-3b75968a468d";
const contact = mapSocialContact({channel:"instagram", external_id:"123", account_scope:"account",
  display_name:"Contact", last_message_id:"9", last_message_role:"user", last_message_text:"hello",
  last_message_at:null, last_activity_at:"2026-11-16T10:00:00Z", pending_id:"draft"});
const pending = {id:"draft", channel:"instagram", convKey:"123:action", suggestions:["hello", "hi"],
  incomingPreview:"hello", hint:"", createdAt:"now", updatedAt:"now"};
const base = {requestId,operation:"approve",contactKey:"instagram:123",pendingId:"draft",
  expectedSuggestions:["hello","hi"],expectedSourceId:"9",expectedAccountScope:"account",identityId:null,identityUpdatedAt:null,text:"hello"};

assert.throws(() => authorizeSocialOwner(null, ownerId, "superadmin"));
assert.throws(() => authorizeSocialOwner({id:modelId,account_id:"other"}, ownerId, "superadmin"));
assert.equal(authorizeSocialOwner({id:modelId,account_id:ownerId}, ownerId, "user").includes("instagram"),false);
assert.equal(authorizeSocialOwner({id:modelId,account_id:ownerId}, ownerId, "superadmin").includes("instagram"),true);
assert.deepEqual(parseContactKey("instagram:123"), {channel:"instagram",externalId:"123"});
for (const key of ["instagram:123:action", "other:12", "telegram:1,or(id.neq.0)", "fanvue:"])
  assert.throws(() => parseContactKey(key));
assert.deepEqual(parseSocialQuery(new URLSearchParams("offset=-3&filter=nope&channel=nope")),
  {search:"",channel:"all",filter:"all",offset:0});

assert.equal(validateSocialCommand(base,contact,pending as never).text,"hello");
const intent = {...pending,suggestions:["[[REMIND]] see you there"],previews:["see you there"]};
assert.equal(validateSocialCommand({...base,expectedSuggestions:intent.suggestions,text:"see you there"},contact,intent as never).text,"see you there");
assert.throws(() => validateSocialCommand({...base,expectedSuggestions:intent.suggestions,text:"[[REMIND]] see you there"},contact,intent as never));
for (const patch of [
  {requestId:"bad"},{operation:"delete"},{contactKey:"instagram:124"},{expectedSourceId:"8"},{expectedAccountScope:"different-account"},
  {identityId:requestId},{pendingId:"another"},{expectedSuggestions:["new"]},{text:"not displayed"},
]) assert.throws(() => validateSocialCommand({...base,...patch},contact,pending as never));
assert.throws(() => validateSocialCommand(base,contact,null));
assert.throws(() => validateSocialCommand({...base,operation:"send_text",text:"🧡".repeat(251)},contact,pending as never));
assert.equal(validateSocialCommand({...base,operation:"send_text",text:"  exact text  "},contact,pending as never).text,"  exact text  ");

const unknown = mapSocialMessage("fanvue",{id:1,role:"user",content:"hello",occurred_at:null,created_at:"2026-11-16T12:00:00Z"});
assert.equal(unknown.occurredAt,null,"Import time must never impersonate provider time");
assert.equal(mapSocialMessage("telegram",{id:2,role:"user",content:"hi",created_at:"2026-11-16T12:00:00Z"}).occurredAt,"2026-11-16T12:00:00Z");
assert.equal(mapSocialMessage("instagram",{id:3,role:"user",content:"[media]",metadata:{kind:"unknown",url:"javascript:alert(1)"}}).attachment?.url,null);
assert.equal((mapSocialContact({...contact,channel:"instagram",external_id:"123",access_token:"secret",prompt:"private"}) as unknown as Record<string,unknown>).access_token,undefined);

const first = mapSocialContact({channel:"telegram",external_id:"1",person_id:"one",identity_status:"verified",display_name:"Alex",last_activity_at:"2026-11-16T12:00:00Z"});
const second = mapSocialContact({channel:"instagram",external_id:"2",person_id:"one",identity_status:"verified",display_name:"Alex",last_activity_at:"2026-11-16T13:00:00Z"});
const candidate = mapSocialContact({channel:"fanvue",external_id:"3",person_id:"separate",candidate_id:"one",identity_status:"recognized",display_name:"Alex"});
const groups=groupSocialPeople([first,second,candidate]);
assert.equal(groups.length,2);
assert.equal(groups[0].contacts.length,2);
assert.equal(groups[1].contacts.length,1,"A matching name or candidate is not a verified group");
console.log("Social sites policy, tenant, stale-draft and timestamp checks passed.");
