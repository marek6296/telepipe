import assert from "node:assert/strict";
import { commandInProgress, commandLabel, createReadScope, freezeIntent, mergeMessages, mergeThread } from "../components/app/social/state.ts";
import type { SocialCommand, SocialCommandInput, SocialMessage, SocialThread } from "../lib/social-types.ts";

const command = { operation: "approve", status: "done", deliveryState: "queued" } as SocialCommand;
assert.equal(commandLabel(command), "Approved · queued", "An accepted IG approval is not a delivered message");
assert.equal(commandLabel({ ...command, deliveryState: "sent" }), "Sent");
assert.equal(commandLabel({ ...command, deliveryState: null }), "Completed");
assert.equal(commandLabel({ ...command, operation: "regenerate" }), "Drafts updated");
assert.equal(commandLabel({ ...command, status: "uncertain" }), "Delivery unconfirmed");

const suggestions = ["First proposal", "Second proposal"];
const intent = freezeIntent({ requestId: "immutable-key", operation: "approve", contactKey: "telegram:1", expectedAccountScope: "creator-original",
  pendingId: "draft-1", expectedSuggestions: suggestions, expectedSourceId: "9007199254740993",
  identityId: "identity-1", identityUpdatedAt: "2026-11-16T12:00:00Z", text: suggestions[1] } as SocialCommandInput);
suggestions[1] = "A replacement from the bot";
assert.equal(intent.text, "Second proposal");
assert.deepEqual(intent.expectedSuggestions, ["First proposal", "Second proposal"], "Retries preserve the exact approved draft version");
assert.equal(intent.requestId, "immutable-key");
assert.equal(intent.expectedSourceId, "9007199254740993");
assert.equal(intent.expectedAccountScope, "creator-original", "Retries cannot change the originating account after a reconnect");

const message = (id: string, content = id): SocialMessage => ({ id, content, channel: "telegram", role: "user", occurredAt: null, recordedAt: "2026-11-16T12:00:00Z", attachment: null });
const older = [message("9007199254740992"), message("9007199254740993")];
const refreshed = mergeMessages(older, [message("9007199254740993", "Updated"), message("9007199254740994")]);
assert.deepEqual(refreshed.map(row => row.id), ["9007199254740992", "9007199254740993", "9007199254740994"]);
assert.equal(refreshed[1].content, "Updated", "Refresh updates overlaps without erasing loaded older history");
assert.equal(refreshed[0].occurredAt, null, "Unknown source timestamps stay unknown");
assert.equal(older[1].content, "9007199254740993", "A refresh cannot mutate another rendered history snapshot");
const lateImport = { ...message("999"), occurredAt: "2026-11-15T12:00:00Z" };
const recent = { ...message("2"), occurredAt: "2026-11-16T12:00:00Z" };
assert.deepEqual(mergeMessages([recent], [lateImport, message("888")]).map(row => row.id), ["888", "999", "2"], "Unknown times sort first; original source chronology beats insertion IDs");
const previous = { contact: { key: "instagram:1" }, messages: [lateImport, recent], hasMore: true, nextBefore: "999" } as SocialThread;
const polled = { contact: { key: "instagram:1" }, messages: [recent], hasMore: true, nextBefore: "2" } as SocialThread;
assert.equal(mergeThread(previous, polled).nextBefore, "999", "A poll preserves the older source-time cursor despite a larger import ID");
assert.equal(mergeThread(previous, { ...polled, contact: { ...polled.contact, key: "instagram:2" } }).messages.length, 1, "Never merge two recipients' histories");
const oldScope = createReadScope("person-a");
const firstRead = oldScope.begin();
const secondRead = oldScope.begin();
assert.equal(oldScope.accepts(firstRead), false, "An older poll cannot overwrite a newer poll");
assert.equal(oldScope.accepts(secondRead), true);
oldScope.dispose();
assert.equal(oldScope.accepts(secondRead), false, "Switching recipient or unmounting invalidates in-flight reads");
assert.equal(oldScope.accepts(oldScope.begin()), false, "An old action callback cannot revive the unmounted reader");
console.log("PASS: Social UI delivery labels, immutable retry intents and history merge");

assert.equal(commandInProgress({...command,status:"sending"}),true);
assert.equal(commandInProgress({...command,status:"done",deliveryState:"sending"}),true);
assert.equal(commandLabel({...command,status:"done",deliveryState:"sending"}),"Sending");
assert.equal(commandInProgress({...command,status:"done",deliveryState:"sent"}),false);
assert.equal(commandInProgress({...command,status:"uncertain"}),false);
