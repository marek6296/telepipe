# Poloautomatický režim odpovedania (semi-auto approval) — návrh

**Dátum:** 2026-08-18
**Stav:** schválený návrh, pripravený na implementačný plán
**Rozsah:** worker (Telegram userbot + Fanvue agent + control bot), Supabase migrácia, web nastavenie
**Nasadenie:** celé naraz (text + fotky + hlasovky + Fanvue platené), deploy až po dokončení

---

## 1. Cieľ

Pridať k modelke tri režimy odpovedania, ktoré platia **naraz pre Telegram aj Fanvue**:

- **Off** — modelka nereaguje vôbec.
- **Auto** — súčasné správanie (AI píše sama: text, hlasovky, fotky podľa persóny a rozvrhu).
- **Semi** — nový režim: každá odpoveď namiesto odoslania príde majiteľovi do Telegram control bota, kde ju schváli, upraví alebo nahradí (text / fotka / hlasovka). Voliteľne sa po 15 minútach bez rozhodnutia odošle sama.

Kľúčová vlastnosť: **v Semi režime sa každá odoslaná vec (vybraný návrh, vlastná správa, fotka, hlasovka) ukladá do histórie ako správa modelky s plným kontextom**, takže prepnutie späť na Auto je plynulé a persóna stále chápe celú konverzáciu — vrátane správ, ktoré majiteľ napísal ručne.

## 2. Kto čo ovláda

- Režim je **per modelka** (`model_id`), riadi obidva kanály jedným nastavením.
- Nastaviteľný na **webe** (prepínač pri modelke) aj v **Telegram control bote** (nahradí terajšie tlačidlo pauzy: Off / Auto / Semi).
- Schvaľovanie prebieha **výhradne v Telegram control bote** (aj pre Fanvue správy — chodia do toho istého bota). Web slúži len na prepnutie režimu, nie na schvaľovanie.
- Per-fan `human_takeover` ("✋ Prevziať chat") ostáva a má prednosť: pre takého fanúšika sa negenerujú ani návrhy.

## 3. Schvaľovacia karta

Keď je Semi zapnuté a príde správa, AI vygeneruje **3 rôzne návrhy** (rôzny vibe, zoradené od najlepšieho — poradie určuje AI) a control bot pošle majiteľovi kartu:

```
💬 Telegram · Lucas
"hey babe, what are you up to tonight 😏"

1️⃣ mmm just got out of the shower, thinking about you 🙈
2️⃣ nothing exciting… wish you were here 😩
3️⃣ being naughty tbh 😏 wanna see?

[1️⃣] [2️⃣] [3️⃣]
[✍️ Napíšem vlastnú]
[📷 Fotka]   [🎤 Hlasovka]
[⏭️ Preskočiť]   [✋ Prevziať chat]
```

- **[1️⃣/2️⃣/3️⃣]** → pošle vybraný návrh (po krátkom „píše…" oneskorení).
- **[✍️ Napíšem vlastnú]** → majiteľ napíše text botovi, pošle sa jeho znenie.
- **[📷 Fotka]** → foto-wizard (§4).
- **[🎤 Hlasovka]** → hlasovkový flow (§5).
- **[⏭️ Preskočiť]** → nič sa nepošle, karta sa zavrie, `pending` sa zruší.
- **[✋ Prevziať chat]** → nastaví `human_takeover` pre tohto fanúšika (žiadne ďalšie návrhy).

Časovanie: v Semi režime sa **ignoruje denný rozvrh a aktívne hodiny** modelky — tempo riadi majiteľ. Po schválení sa pridá krátke ľudské „píše…" oneskorenie (podľa dĺžky správy, `humanize.typing_delay`), aby to nevyzeralo roboticky. Hard-gates ostávajú: blokovaný fanúšik, `human_takeover`, a Telegram flood (pri floode sa aj po schválení počká — chráni to jej účet pred banom).

## 4. Foto-wizard

**Telegram (len zadarmo):**
1. `[📷 Fotka]` → zoznam nahratých fotiek modelky (`photos`, aktívne), zobrazené ako obrázky, každý s `[✅ Táto]` (stránkované).
2. Vybraná fotka → popis: `[1️⃣][2️⃣][3️⃣ návrh]` `[✍️ vlastný]` `[bez popisu]`.
3. Odošle fotku + popis, zaznamená `photo_send`, uloží do histórie `[poslala fotku: …]`.

**Fanvue (zadarmo aj platené):**
1. `[📷 Fotka]` → výber priečinka z vaultu: `[🟢 SFW] [🔴 NSFW] [📢 Post]` (podľa `fv_folders.role`).
2. Priečinok → médiá (`fv_media` v priečinku) ako obrázky, každé s `[✅ Táto]`.
3. Vybraté médium → `[💚 Zadarmo] [💰 Za peniaze]`.
   - **Zadarmo** → popis (návrhy / vlastný / bez) → `Fanvue.send(media_uuids=[uuid])`.
   - **Za peniaze** → „Napíš cenu v $ (číslo):" → napr. `50` → „Cena $50 — potvrdiť? [✅] [✏️ zmeniť]" → popis → `Fanvue.send(media_uuids=[uuid], price_cents=5000)`.
4. Uloží do histórie `[poslala fotku: …]` resp. `[poslala platenú fotku $50: …]`.

Cena a vlastný popis využívajú existujúci `_awaiting` value-entry pattern control bota (`_ask_value` → `_on_value` → `_apply_value`).

## 5. Hlasovka

1. Majiteľ vyberie návrh alebo napíše text, potom `[🎤 Hlasovka]`.
2. Worker vygeneruje ogg (ElevenLabs, cez existujúci `livevoice.speak`) a **pošle ho najprv majiteľovi na vypočutie** s `[✅ Poslať fanúšikovi] [❌ Zahodiť]` — schvaľuje sa aj zvuk.
3. Po `[✅]` sa hlasovka odošle fanúšikovi (`send_file(voice_note=True)`), uloží do histórie `(hlasovka) <text>`.

Ak AI sama inklinovala k hlasovke alebo fotke (dnes to rozhoduje inline v `_reply_locked` / `_reply`), karta to zobrazí ako **tip** („AI navrhuje skôr hlasovku"), ale rozhoduje majiteľ.

## 6. Auto-odoslanie po 15 minútach (voliteľné)

Samostatný prepínač pri modelke, **účinný len v Semi režime**:

- **Zapnuté** → ak sa `pending` nerozhodne do **15 minút** (fixne), worker odošle **prvý (AI-top) návrh** rovnakou send-cestou, ako keby ho vybral majiteľ. „Rozhodne ona, ktorý pošle" = poradie návrhov je rozhodnutie AI.
- **Vypnuté** → `pending` čaká na rozhodnutie neobmedzene.

Odpočet stráži poller vo workeri (rovnaká kadencia ako `voice_jobs` poller / sweeper), takže beží aj keď je web aj Telegram zavretý.

## 7. Supersede pri novej správe

Keď fanúšik napíše ďalšiu správu, kým je `pending` v stave `awaiting`:
- stará karta sa zruší (`pending` → `superseded`, control message sa upraví na „(neaktuálne)"),
- AI vygeneruje nový `pending` k aktuálnej konverzácii.

Platí v oboch prípadoch (s aj bez 15-min fallbacku), aby majiteľ nikdy neschvaľoval zastarané návrhy. Nadväzuje na existujúcu debounce logiku.

## 8. Dátový model

### 8.1 `settings` (rozšírenie)
- `reply_mode text not null default 'auto' check (reply_mode in ('off','auto','semi'))`
- `semi_auto_fallback boolean not null default false` — 15-min auto-odoslanie, účinné len pri `reply_mode='semi'`.
- `ai_paused` ostáva ako systémová núdzová pauza (flood) — nezávislá od `reply_mode`.

Rozhodovanie workera: automaticky posielaj len ak `reply_mode='auto'` a nie `ai_paused`. Pri `reply_mode='semi'` choď do schvaľovacieho toku. Pri `reply_mode='off'` neposielaj nič.

### 8.2 `pending_replies` (nová tabuľka)
Durabilná fronta čakajúcich rozhodnutí (vzor podľa `voice_jobs`), aby prežila presun modelky na inú repliku workera.

```
pending_replies (
  model_id      uuid not null,
  id            uuid primary key default gen_random_uuid(),
  channel       text not null check (channel in ('telegram','fanvue')),
  conv_key      text not null,        -- tg_id (text) alebo fan_uuid
  status        text not null default 'awaiting'
                  check (status in ('awaiting','sent','skipped','superseded')),
                  -- awaiting → sent (manuálne alebo 15-min fallback) | skipped (Preskočiť)
                  --         → superseded (fanúšik napísal novú správu)
  suggestions   jsonb not null,       -- ["…","…","…"] zoradené od najlepšieho
  incoming_preview text not null default '',  -- správa fanúšika (pre kartu)
  chosen_text   text,                 -- čo sa reálne poslalo (text/popis)
  kind          text,                 -- 'text' | 'photo' | 'voice'
  media_ref     text,                 -- photo id / fv_media uuid
  price_cents   integer,              -- Fanvue platené, inak null
  control_msg_id bigint,              -- id správy karty (na edit/zrušenie)
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  decided_at    timestamptz
)
```

Indexy: `(model_id, status, created_at)` pre poller; `(model_id, channel, conv_key)` pre supersede lookup.
RLS: service_role plný prístup; `authenticated` len SELECT vlastných (cez `model_id` → účet), aby web vedel prípadne ukázať počet čakajúcich. Zápis výhradne service_role.
RPC: `claim_pending_reply` (atomické `awaiting`→`sent`, aby poller a callback nekolidovali), po vzore `claim_voice_job`.

## 9. Zmeny v kóde

### Worker
- **nový modul `pending.py`**: `create_pending(...)`, `get_pending(id)`, `claim_pending(id)`, `supersede_open(channel, conv_key)`, `fallback_due(max_age=15min)` — vráti `awaiting` staršie ako 15 min pre modelky so `semi_auto_fallback=true`.
- **`llm.py`**: nová metóda `suggest(system, history, n=3)` — jedno volanie, 3 varianty, parsované do zoznamu (zoradené od najlepšieho).
- **`userbot.py`**: v `_reply_locked` odbočka pri `reply_mode='semi'` — namiesto send bloku: `supersede_open` → `suggest` → `create_pending` → `control.notify` karta → `pending_reply=True` → return. Nový vstup `send_approved(pending, choice)` znovupoužije existujúci send blok (`send_message` + `add_message` + `_post_send_update`).
- **`fanvue_agent.py`**: rovnaká odbočka v `_reply`; send cez `Fanvue.send`, kontext cez `fv_messages`.
- **`control_bot.py`**: celé schvaľovacie UI — render karty, callbacky (výber návrhu, vlastná správa, foto-wizard, cena, hlasovka + jej preview), tri-state v hlavnom menu, obnova `awaiting` po štarte repliky. Nové callback heady (napr. `ap:` approve-pick, `ac:` approve-custom, `af:` foto, `av:` voice).
- **poller** (nový `start_approval_poller` alebo napojenie na existujúci sweeper): pre modelky so `semi_auto_fallback=true` odosli `awaiting` staršie ako 15 min prvým návrhom.

### Web
- Prepínač **Off / Auto / Semi** + prepínač **15-min auto-odoslanie** pri modelke (číta/zapisuje `settings.reply_mode`, `settings.semi_auto_fallback`). Umiestnenie: sekcia nastavení modelky (napr. pri persóne/behavior alebo dedikovaná „Replies" karta).
- Read helper na `reply_mode` (dnes sa číta `ai_paused` cez `getPausedMap`).

## 10. Invarianty / čo sa nesmie pokaziť

- **Auto režim ostáva bajt-za-bajt ako dnes** — odbočka sa aktivuje len pri `reply_mode='semi'`.
- **Každá odoslaná vec v Semi sa uloží ako `role='assistant'`** so správnym markerom a prebehne `_post_send_update` (clear `pending_reply`, `last_reply_at`, funnel, pamäť/summary) — inak by sa po návrate na Auto rozbila kontinuita persóny.
- **Vlastná (ručne napísaná) správa** sa ukladá rovnako → persóna sa z nej učí.
- **Flood a blokovaný fanúšik** sú tvrdé gates aj v Semi (chránia účet).
- **Idempotencia odoslania**: `claim_pending_reply` zaručí, že poller (15 min) a manuálne kliknutie nemôžu poslať dvakrát.

## 11. Zámerne mimo v1 (YAGNI)

- Nastaviteľná dĺžka fallbacku (fixne 15 min).
- Schvaľovanie na webe (len prepínač režimu; schvaľuje sa v Telegrame).
- Preview textových návrhov na webe.
- Telegram Stars / platené fotky na Telegrame (Telegram DM nemá paywall — platené len Fanvue).
