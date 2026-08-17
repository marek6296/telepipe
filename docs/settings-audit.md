# Settings audit — every client-facing control, end to end

Each row: **UI field (tab) → write path → DB column → who reads it → effect → verdict.**

Verdicts:

- **OK** — writes, lands, worker reads it, value changes behaviour.
- **BROKEN (fixed)** — did not work for the client; fixed in this pass.
- **MISMATCH (fixed)** — control worked but the label/help promised something the
  worker does not do; copy corrected to the worker's actual contract.
- **DEAD** — written but never read (or rendered but never written).
- **HIDDEN** — worker reads it, no UI. Listed at the bottom with a proposal.

Line references are `worker/src/<file>:<line>` unless stated otherwise.

## Summary

| Verdict | Count |
|---|---|
| OK | 109 |
| BROKEN (fixed) | 1 |
| MISMATCH (fixed) | 3 |
| HIDDEN → wired in this pass | 3 |
| DEAD | 1 |
| **Total client-facing controls** | **117** |
| HIDDEN, reported only (no UI at all) | 5 |

No migration was required: every `authenticated` grant and every check constraint
already matched what the UI sends. All fixes were in `web/`.

---

## Telegram tab — connection wizard

| UI field (step) | Write path | DB column | Read by | Effect | Verdict |
|---|---|---|---|---|---|
| api_id (1) | `startTelegramLoginAction` | `tg_login_jobs.api_id`, `models.tg_api_id` | `login_jobs.py`, `config.py`, `runner.py` | MTProto app id | OK |
| api_hash (1) | same | `tg_login_jobs.api_hash_enc` (AES) | `login_jobs.py` decrypts | MTProto app hash | OK |
| Phone (2) | same | `tg_login_jobs.phone` | `login_jobs.py` | which account logs in | OK |
| Login code (3) | `submitLoginCodeAction` | `tg_login_jobs.code_enc` + `phase` | `login_jobs.py` | completes sign-in | OK |
| 2FA password (3) | `submitLoginPasswordAction` | `tg_login_jobs.password_enc` + `phase` | `login_jobs.py` | completes 2FA | OK |
| Start over (3) | `cancelLoginJobAction` | `tg_login_jobs.phase='error'` | — | abandons the job | OK |
| Bot token (4) | `saveControlBotAction` (service key) | `models.control_bot_token_enc` | `control_bot.py` | control bot identity | OK |
| **Your chat ID (4)** | `saveControlBotAction` | `models.owner_chat_id` | `config.py`, `control_bot.py`, `userbot.py` | where alerts go | **BROKEN (fixed)** |
| Activate (5) | `setModelStatusAction` → RPC `set_model_status` | `models.status` | `registry.py`, `main.py` | worker claims the model | OK |

**BROKEN — owner chat ID could not be changed on its own.** The Save button was
`disabled={pending || !token || !chatId}` and the token box always mounts empty
(the stored token is encrypted and never comes back to the browser). A client who
mistyped their chat ID had to fetch the bot token from @BotFather again just to
correct one number. Fixed: an empty token now means "keep the stored one" —
`saveControlBotAction` verifies a token already exists (`controlBotConfigured`)
and updates only `owner_chat_id`; the button accepts a chat-ID-only save when
`alreadySaved`. A first-time save still requires a valid, `getMe`-verified token.

---

## Persona tab

All 13 fields reach the LLM system prompt built by `persona.build_system_prompt`.

| UI field | DB column | Prompt site | Section | Verdict |
|---|---|---|---|---|
| Name | `persona.name` | `persona.py:255` | `Si {name}.` | OK |
| Age | `persona.age` | `persona.py:259` | `Máš {age} rokov.` | OK |
| City | `persona.city` | `persona.py:261`, `:358` | identity + local clock (`local_time_line`) | OK |
| Languages she speaks | `persona.languages` | `persona.py:606`, `:1015` | `ČO OVLÁDAŠ ZA JAZYKY` + reminder | OK |
| Reply language | `persona.language` | `persona.py:269`, `:1013` | `JAZYK ODPOVEDÍ` + closing reminder | OK |
| Backstory | `persona.backstory` | `persona.py:272` | `O TEBE` | OK |
| Tone | `persona.tone` | `persona.py:273` | `TÓN` | OK |
| Message style | `persona.msg_style` | `persona.py:274` | `ŠTÝL SPRÁV` | OK |
| What she never does | `persona.boundaries` | `persona.py:275` | `HRANICE` | OK |
| Extra instructions | `persona.extra_rules` | `persona.py:276` | `ĎALŠIE POKYNY` | OK |
| Examples of her writing | `persona.examples` | `persona.py:982` | `TAKTO PÍŠEŠ TY` (last, nearest generation) | OK |
| How she leads to it | `persona.funnel_rules` | `persona.py:852` | `AKO NAVIESŤ NA OBSAH` | OK |
| **Your link** | `persona.cta_link` | `persona.py:856-863` | `ODKAZ JE TERAZ POVOLENÝ` | **MISMATCH (fixed)** |

`cta_link` is the only link that can leave: it passes through
`checkout.attributed()` (`persona.py:859`) so the fan can be matched on Fanvue,
and empty means the "link allowed" section is never emitted at all.

**MISMATCH — the link help hardcoded a limit that is a setting.** It read
"at most 2 links per hour across all chats". The real gate is
`behavior.max_links_per_hour` (`userbot.py:1095-1103`), which the client sets on
the Behavior tab — 2 is only the default. The 48-hour per-fan cooldown and the
6-message floor are real (`config.py:148-149`, `funnel.can_send_link`). Copy now
points at the Behavior setting instead of quoting a number that may be wrong.

Covered by `worker/tests/test_nastavenia_klienta.py::TestPersonaVPrompte` and
`::TestOdkazKlienta`.

---

## Behavior tab

| UI field | DB column | Read by | Effect | Verdict |
|---|---|---|---|---|
| Mode | `behavior.mode` | `persona.py:265` | `_REAL_MODE` vs `_AI_MODE` block | OK |
| Spice level | `behavior.heat` | `persona.py:823` | one of three `_HEAT_RULES` | OK |
| Slang | `behavior.slang` | `persona.py:296`, `userbot.py:999` | prompt rule **and** post-generation `humanize.soften_slang` | OK |
| **Asks a question back** | `behavior.question_chance` | `userbot.py:527-530` | `can_ask` dice roll | **MISMATCH (fixed)** |
| Cheeky joke | `behavior.gag_chance` | `userbot.py:532` | `gags.maybe_pick` | OK |
| Type without accents | `behavior.no_diacritics` | `persona.py:292`, `userbot.py:1007` | prompt rule + strip pass | OK |
| Waves of activity | `behavior.activity_waves` | `behavior.py:352`, `userbot.py:394` | `wave_factor` 1.0 vs 0.12–1.35 | OK |
| Awake from / Until | `behavior.active_start_min/_end_min` | `behavior.in_active_window`, `persona.py:401` | reply window, wind-down | OK |
| Her time zone | `behavior.active_tz` | `userbot.py:323`, `:1808` | drives her whole local day | OK |
| Morning messages | `behavior.morning_enabled` | `userbot.py:1715` | outreach loop on/off | OK |
| Morning messages per day | `behavior.morning_max_per_day` | `userbot.py:1744` | `outreach.due(limit=…)` | OK |
| Greets again after | `behavior.greeting_gap_hours` | `behavior.greeting_allowed`, `persona.py:420` | greeting allowed or forbidden | OK |
| Waits for him to finish (min/max) | `debounce_min_s/_max_s` | `behavior.debounce_delay` | message coalescing | OK |
| Before she reads (min/max) | `read_delay_min_s/_max_s` | `behavior.read_delay` | delay to "seen" | OK |
| Before she replies (min/max) | `reply_delay_min_s/_max_s` | `behavior.reply_delay` | delay to first bubble | OK |
| Attentive mode | `quick_reply_chance` | `behavior.quick_reply` | fast-path probability | OK |
| Attentive reply after (min/max) | `quick_reply_min_s/_max_s` | `behavior.quick_reply` | scaled by his message length | OK |
| Attentive: seen within | `quick_read_max_s` | `behavior.quick_reply` | fast-path read delay | OK |
| Leaves him on read | `seen_only_chance` + `min/max_s` | `behavior.seen_only_delay` | read-then-wait | OK |
| Walks away from phone | `long_pause_chance` + `min/max_s` | `behavior.long_pause_delay` | mid-chat gap | OK |
| Forgets to reply for hours | `defer_reply_chance` + `defer_min/max_s` | `behavior.should_defer_reply` | hours-long deferral | OK |
| Replies per hour | `max_replies_per_hour` | `userbot.py:343`, `:1735` | global hourly cap | OK |
| Links per hour | `max_links_per_hour` | `userbot.py:1095-1103` | global link cap; 0 = never | OK |
| Gap between photos | `photo_cooldown_min` | `userbot.py:1213` | per-fan photo cooldown | OK |
| Summarise every | `summary_every` | `userbot.py:1605` | rolling summary cadence | OK |
| **Conversations at once** | `max_active_chats` | `userbot.py:352`, `:1663` | `limity.ma_miesto`; 0 = off | **HIDDEN → wired** |
| **A slot frees up after** | `chat_slot_min` | `userbot.py:1666` | how long a chat holds a slot | **HIDDEN → wired** |
| **People she writes to first** | `max_outreach_per_hour` | `userbot.py:1676`, `:1749` | `limity.smie_oslovit`; 0 = off | **HIDDEN → wired** |

**HIDDEN → wired: the three anti-ban caps.** `max_active_chats`, `chat_slot_min`
and `max_outreach_per_hour` are the worker's `behavior.SAFETY_FIELDS` — the
knobs that decide whether the account reads as one person or as a broadcaster.
The worker has read them since day one and the `authenticated` grant already
allowed writing them, but there was no dashboard field and the server action
whitelist dropped them, so only the Telegram control bot could set them. Added
to the "Limits and memory" card under a **Looking like one person** group, plus
`INTEGERS` in `behavior/actions.ts` and `BEHAVIOR_COLUMNS` in `behavior/page.tsx`.
Ranges follow the worker: 0 disables the two caps (`limity.py:45`, `:94`), while
`chat_slot_min` starts at 1 because 0 there would silently disable
`max_active_chats` too.

**MISMATCH — "Asks a question back" is overridden early in a chat.**
`userbot.py:528-529` raises the chance to at least 0.8 for the first 20 messages
(`persona.EARLY_PHASE`), so a client setting 20% actually got 80% during the
phase that matters most. Zero is still honoured as zero. The help text now says
so instead of implying the slider is absolute.

---

## Voice tab

Full chain verified per setting: UI → `behavior` column → decision site → audio.

| UI field | DB column | Read by | Effect | Verdict |
|---|---|---|---|---|
| Send voice messages | `voices_enabled` | `userbot.py:882` | master gate on the send condition | OK |
| Voice picker | `eleven_voice_id` | `userbot.py:887`, `:922` | the ElevenLabs voice used for TTS | OK |
| How often she sends one | `voice_chance` | `userbot.py:904` → `livevoice.should_speak` | probability point | OK |
| Speaking tempo | `voice_tempo` | `userbot.py:925` → `livevoice._tempo_filter` | ffmpeg `atempo` (pitch-preserving) | OK |
| Where she is recording | `voice_ambience` | `userbot.py:913` | `eleven.AMBIENCES` prompt + `livevoice._AMBIENCE_MIX` filter | OK |
| Recording quality | `voice_strength` | `userbot.py:924` | `livevoice._RECIPES` (band, bitrate, bit-crush, hiss) | OK |
| Background volume | `voice_ambience_level` | `userbot.py:926` → `livevoice.ambience_mix` | room gain under the voice | OK |
| He asks for one | `voice_when_asked` | `speech.py:158` | exception to the dice roll | OK |
| He doubts she is real | `voice_when_doubted` | `speech.py:159` | exception (also bypasses cooldown, `userbot.py:874`) | OK |
| He sends voice notes | `voice_when_he_voices` | `speech.py:160` | exception | OK |
| She is out and busy | `voice_when_away` | `speech.py:161` | exception | OK |
| Saying good night | `voice_on_goodnight` | `speech.py:162` | exception | OK |
| He is pushing, not converted | `voice_when_hot` | `speech.py:163`, `userbot.py:718` | exception + `hot_voice` prompt block | OK |

Value sets agree across all four places — UI `AMBIENCE`, the server action
`ENUMS`, `behavior.AMBIENCE_CYCLE`, `eleven.AMBIENCES` and
`livevoice._AMBIENCE_MIX` hold exactly the same nine rooms; `voice_strength` is
`soft|real|rough` in all of them and each has a distinct `_RECIPES` entry.

**Slider ranges are inside what the pipeline tolerates.** The tempo slider allows
0.5–2.0 and `livevoice._tempo_filter` clamps to exactly 0.5–2.0, which is what a
single ffmpeg `atempo` accepts; `wobble_tempo` re-clamps after adding jitter, so
even the extremes cannot push the mix out of range. `voice_ambience_level` 0–1
maps through per-room gains up to 2.10 (`outside`), and `none` mixes to hard
silence. A tempo the model asks for in `[HLAS: …]` is only honoured inside
0.85–1.45 (`speech.tempo_from`); outside that the client's setting wins.

Covered by `worker/tests/test_nastavenia_klienta.py::TestHlasovky`.

---

## Photos tab

| UI field | Write path | DB column | Read by | Verdict |
|---|---|---|---|---|
| Upload | direct storage upload → `createPhotoAction` | `photos.url` | `photos.py`, `userbot.py` | OK |
| Caption | `updatePhotoAction` | `photos.caption` | `persona.py:775`, `photos.py` | OK |
| Situation | same | `photos.situation` | `persona.py:776`, `facts.py` | OK |
| Set | same | `photos.collection` | `photos.py` | OK |
| Good times of day | same | `photos.parts` | `photos.py`, `topics.py` | OK |
| Spicy | same | `photos.spicy` | `photos.py`, `fanvue_agent.py` | OK |
| In rotation | same | `photos.active` | `photos.py` | OK |
| Delete | `deletePhotoAction` | row + storage object | — | OK |

`DAY_PARTS` in `web/lib/photos.ts` is `poobede | podvecer | vecer | noc`, which
matches `behavior.part_of_day` exactly. The action's whitelist covers every key
the UI sends, so the `Unknown field` branch is unreachable from this screen.

---

## Fanvue tab — connection

| UI control | Write path | DB column | Read by | Verdict |
|---|---|---|---|---|
| Connect | OAuth route | `fanvue.connected`, tokens | `fanvue_tenant.py` | OK |
| Disconnect | `disconnectFanvueAction` (service key) | clears tokens, `connected=false` | — | OK |
| Reply on Fanvue (on/off) | `setFanvueEnabledAction` (service key) | `fanvue.enabled` | `fanvue_agent.py`, `fanvue_tenant.py` | OK |
| Sync vault | `requestVaultSyncAction` | `fanvue_sync_requests` row | `fvvault.VaultSync` | OK |

The enable toggle only succeeds on a connected account (`.eq("connected", true)`)
and the client has no direct grant on those columns — verified below.

---

## Fanvue tab — agent settings

All 21 fields write through `saveFanvueSettingsAction` with the **user-scoped**
client (column grants + `fanvue_owner_update` from migration 015), and every
UI range equals its DB check constraint.

| UI field | DB column | Read by | Verdict |
|---|---|---|---|
| Greet new subscribers | `greet_new` | `fanvue_agent.py` | OK |
| Spice level | `heat` | `fanvue_agent.py:247`, `persona.py` | OK |
| Gets to know him for | `discovery_msgs` | `fanvue_agent.py` | OK |
| Summarise every | `summary_every` | `fanvue_agent.py:911` | OK |
| Waits before replying (min/max) | `reply_min_s`, `reply_max_s` | `fanvue_agent.py` | OK |
| Answers from / Until | `active_start_min`, `active_end_min` | `fanvue_agent.py` | OK |
| Offers paid content | `sell_content` | `fanvue_agent.py`, `fvflow.py`, `fvvoice.py` | OK |
| Thanks for every purchase | `thank_purchases` | `fvflow.py` | OK |
| First offer after | `offer_after_msgs` | `fanvue_agent.py`, `fvflow.py` | OK |
| Gap between offers | `offer_cooldown_h` | `fanvue_agent.py`, `fvflow.py` | OK |
| Brings it up herself after | `nudge_after_msgs` | `fvflow.py` | OK |
| Sends voice notes | `voices_enabled` | `fvvoice.py:66` | OK |
| Price of explicit voice note | `voice_price_cents` | `fanvue_agent.py` | OK |
| Attaches photos | `send_photos` | `fanvue_agent.py` | OK |
| Free photos per fan | `free_photo_max` | `fvflow.py` | OK |
| Posts to the feed | `posting_enabled` | `fvmedia.py` | OK |
| How often | `post_every_h` | `fvmedia.py` | OK |
| Who sees it | `post_audience` | `fanvue_agent.py` | OK |
| Fanvue instructions | `extra_rules` | `fanvue_agent.py`, `persona.py` | OK |

---

## Fanvue tab — vault

| UI control | Write path | DB column | Read by | Verdict |
|---|---|---|---|---|
| Folder role | `saveFolderAction` | `fv_folders.role` | `fvmedia.role_of:34`, `fanvue_agent.py:416` | OK |
| Folder default price | `saveFolderAction` | `fv_folders.price_cents` | `fvmedia.py`, `fanvue_agent.py` | OK |
| Photo caption | `saveMediaAction` | `fv_media.caption` | `fvmedia.py:115` (matching) | OK |
| Photo price | `saveMediaAction` | `fv_media.price_cents` | `fanvue_agent.py` | OK |
| On / Off | `saveMediaAction` | `fv_media.active` | `fvmedia.py` | OK |
| **Explicit** | `saveMediaAction` | `fv_media.spicy` → `spicy_override` | `fvmedia.is_spicy:56` | **MISMATCH (fixed)** |

Folder roles agree exactly: UI `FOLDER_ROLES`, the action's `FOLDER_ROLES` and
`fvmedia.ROLES` are all `ignore | sfw | nsfw | post`.

**MISMATCH — the "Explicit" chip does more than the help text claimed.** The copy
said *"'Explicit' is a label for you: when she picks a photo for a chat, the
folder role decides."* That was true before migration 016. It is not true now:
`fvmedia.is_spicy` (`:56-59`) reads `spicy_override` first and only falls back to
the folder when it is `NULL`. The chip is wired correctly — the `BEFORE UPDATE`
trigger `fv_media_spicy_effective` translates a write to the derived `spicy`
column into an explicit `spicy_override` — so the control works; only the copy
was stale. Text now says the photo overrides its folder in both directions.

---

## Account tab and model chrome

| UI control | Write path | Target | Verdict |
|---|---|---|---|
| Change password | `changePasswordAction` | Supabase Auth (re-auth required) | OK |
| Sign out everywhere | `signOutEverywhereAction` | Auth sessions | OK |
| Connect ElevenLabs | `connectElevenAction` → RPC `set_account_eleven_key` | `accounts.eleven_key_enc` | OK |
| Disconnect ElevenLabs | `disconnectElevenAction` → RPC `clear_account_eleven_key` | `accounts.eleven_key_enc=''` | OK |
| Delete account | — (disabled placeholder) | — | **DEAD** |
| Rename model | `renameModelAction` | `models.name` | OK |
| Delete model | `deleteModelAction` | cascade delete | OK |
| Activate / Pause | RPC `set_model_status` | `models.status` | OK |

The key is per **account**, not per model (migration 017), and only ever travels
one way: encrypted in the server action, written by a `security definer` RPC, and
read back only as the boolean `has_account_eleven_key()`. The worker resolves it
account-first (`db.py`). "Delete account" is a deliberate placeholder
("Self-service deletion is not live yet") but is an inert control today.

---

## HIDDEN — worker reads it, no UI

Not implemented in this pass; each needs a design decision, not just a field.

1. **`settings.ai_paused`** — the real "stop replying" switch
   (`userbot.py:310`, `:1816`). The control bot toggles it
   (`control_bot.py:224`) and, worse, the worker sets it **itself** on
   `PeerFloodError` (`userbot.py:1071`) when Telegram flags the account. The
   dashboard neither shows nor clears it, so a flagged client sees a green
   "active" model that answers nobody, recoverable only from Telegram.
   *Proposal:* surface it on the model header next to the power button as a
   distinct "AI paused — Telegram flagged this account" state with a resume
   action. The `authenticated` role already has full grant on the column, so this
   is UI-only. **Highest-value item left.**
2. **`models.owner_as_client`** (`config.py:244`, `userbot.py:174`) — lets the
   owner chat with their own model for testing. *Proposal:* a switch on the
   Telegram tab next to the owner chat ID. Needs a `SELECT`→`UPDATE` grant.
3. **`models.voice_only_ids`** (`config.py:245`, `userbot.py:625`, `:835`) —
   fans who always get voice instead of text. *Proposal:* a chip list on the
   Voice tab; needs new UX for entering Telegram ids, so not trivial.
4. **`fv_media.fits`** (`fvmedia.py:115`, `voices.py:135`) — extra matching text
   per vault item, already granted to `authenticated`, never written by the UI.
   `caption` covers the same job, so value is low. *Proposal:* fold into the
   caption box as a second line, or drop the column.
5. **`fv_media.spicy_override` reset** — the chip can only set `true`/`false`,
   never back to `NULL` ("follow the folder"). *Proposal:* make the chip
   tri-state; needs a small UI affordance.

`photos.sent_count` is worker-owned but carries a blanket `UPDATE` grant. The UI
never sends it and the action whitelist rejects it, so it is not reachable from
the dashboard — a client could only skew their own photo rotation. Worth
tightening the grant next time `photos` is touched.

---

## Step 2 evidence — write path proven, not just read

Executed against `cggsyshfdjycfqrhtjld` as a **simulated authenticated user**
(`set role authenticated` + `request.jwt.claims`), on a throwaway account
(`aaaaaaaa-…a17d`) and model (`a0694876-…`) created through the same insert the
UI performs. Every write was the literal value the form sends, including range
extremes.

- **88 column writes attempted.** All 79 whitelisted columns landed and read
  back with the written value — every Behavior enum, boolean and numeric edge
  (`active_start_min=1439`, `defer_max_s=172800`, `voice_tempo=2.0`,
  `voice_ambience_level=1`), all 13 Persona fields, all 21 Fanvue settings, and
  the 3 newly wired safety caps.
- **10 protected columns correctly refused** with `42501 permission denied`:
  `behavior.eleven_key`, `behavior.eleven_key_enc`, `fanvue.enabled`,
  `fanvue.connected`, `fanvue.access_token_enc`, `fanvue.last_post_at`,
  `fanvue.media_synced_at`, `models.status`, `models.control_bot_token_enc`,
  `models.owner_as_client`.
- **No check-constraint conflicts.** Every UI-offered value passed; no select
  offers a value the DB would reject, and no numeric range exceeds its check.
- **RPCs:** `set_model_status` walked `draft→active→paused→active` and correctly
  refused `active→draft` (*"transition not allowed"*) and a foreign model
  (*"model not found"*). `set_account_eleven_key` rejected both an empty value
  and a plaintext one (*"must be encrypted (nonce:ct:tag)"*), accepted a
  well-formed one, and `has_account_eleven_key` flipped `false→true→false`
  around `clear_account_eleven_key`. Reading `accounts.eleven_key_enc` directly
  was denied.
- **Queue paths:** `tg_login_jobs` insert + `code_enc`/`password_enc` updates
  succeeded; reading `code_enc` back and writing `tmp_session_enc` were denied.
  `fanvue_sync_requests` insert succeeded and the second pending insert hit
  `23505` on `fanvue_sync_pending_one_idx` — exactly the code the action treats
  as success.
- **Tenant isolation:** an update aimed at Simona's `persona` from the throwaway
  session affected zero rows (RLS no-op) and her values were confirmed unchanged.
- **Select path:** the new `BEHAVIOR_COLUMNS` list, including the three added
  columns, returned successfully under the same JWT.

### Production safety

Snapshot of `models`, `persona`, `behavior`, `fanvue`, `accounts`, `fv_folders`,
`fv_media`, `photos` taken **before** any write and diffed **after** cleanup with
a symmetric `EXCEPT` in both directions:

| Table | Differing rows |
|---|---|
| accounts, behavior, fanvue, fv_folders, fv_media, persona, photos | **0** |
| models | 2 rows, `heartbeat_at` only |

The only movement is the live worker's own liveness ping. Every settings column,
including `updated_at`, is byte-identical for both Simona and Mio. Baseline
restored: 2 models, 2 accounts, 0 leftover login jobs or sync requests. The
throwaway account, model and the temporary `audit_snap` schema were dropped.

---

## New tests

`worker/tests/test_nastavenia_klienta.py` — 46 tests, all green. Not "the column
is read somewhere" but "a different value gives a different outcome":

- every Persona field appears in the composed prompt, under its intended heading,
  and an empty persona produces no empty sections;
- `cta_link` is the link that ships, carries its `client_reference_id`
  attribution, and an empty one removes the "link allowed" block entirely;
- `mode`, `heat`, `slang`, `no_diacritics` each select a different prompt rule;
  `slang` additionally rewrites text post-generation;
- active window semantics the UI promises (equal start/end = 24/7, windows across
  midnight) and `greeting_gap_hours` moving the greeting threshold;
- the three new safety caps, including `0 = off` and "whoever holds a slot always
  passes", plus a guard that they survive `Behavior.from_row`;
- UI slider extremes survive `from_row`, inverted min/max ranges do not raise,
  chance 0 means never and 1 means always;
- `voice_chance` 0/1 over 50 seeds, each of the six voice exceptions toggled
  independently, every ambience present in both the sound map and the mix, rooms
  audibly distinct, every strength with its own recipe, tempo reaching `atempo`,
  and `wobble_tempo` staying inside ffmpeg's range at both slider extremes.

Full suite: **1500 passed, 2 deselected** (baseline 1454 + 46 new).
Web: `tsc --noEmit` clean, `eslint` clean, `next build` green.
