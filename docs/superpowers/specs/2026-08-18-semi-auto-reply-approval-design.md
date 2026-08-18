# Poloautomatický režim odpovedania (semi-auto approval) — návrh

**Dátum:** 2026-08-18
**Stav:** schválený návrh, pripravený na implementačný plán
**Rozsah:** worker (Telegram userbot + Fanvue agent + control bot), Supabase migrácia, web nastavenie
**Nasadenie:** celé naraz (text + fotky + hlasovky + Fanvue platené), deploy až po dokončení

---

## 1. Cieľ

Pridať tri režimy odpovedania, **nastaviteľné samostatne pre Telegram a pre Fanvue** (nie jedno spoločné prepnutie — klient si vyberie, na ktorom kanáli chce poloautomat):

- **Off** — modelka na danom kanáli nereaguje vôbec.
- **Auto** — súčasné správanie (AI píše sama: text, hlasovky, fotky podľa persóny a rozvrhu).
- **Semi** — nový režim: každá odpoveď namiesto odoslania príde majiteľovi do Telegram control bota, kde ju schváli, upraví alebo nahradí (text / fotka / hlasovka). Voliteľne sa po nastavenom počte minút bez rozhodnutia odošle sama.

Príklad: klient môže mať Telegram = Auto a Fanvue = Semi — vtedy chodia na schválenie len Fanvue správy, Telegram beží sám.

Kľúčová vlastnosť: **v Semi režime sa každá odoslaná vec (vybraný návrh, vlastná správa, fotka, hlasovka) ukladá do histórie ako správa modelky s plným kontextom**, takže prepnutie späť na Auto je plynulé a persóna stále chápe celú konverzáciu — vrátane správ, ktoré majiteľ napísal ručne.

## 2. Kto čo ovláda

- Režim je **per modelka a per kanál**: samostatný pre Telegram, samostatný pre Fanvue.
- Nastaviteľný na **webe** — v **Telegram sekcii** modelky sa zapína Telegram režim, v **Fanvue sekcii** sa zapína Fanvue režim (dve nezávislé nastavenia).
- Nastaviteľný aj v **Telegram control bote** — hlavné menu ukáže oba kanály zvlášť (napr. „Telegram: Auto / Fanvue: Semi") s vlastným prepínačom pre každý. Nahradí terajšie jediné tlačidlo pauzy.
- Schvaľovanie prebieha **výhradne v Telegram control bote** — aj pre Fanvue správy, tie chodia do toho istého Telegram bota (control bot je jediné miesto schvaľovania pre oba kanály). Web slúži len na prepnutie režimu, nie na schvaľovanie.
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

## 6. Auto-odoslanie po nastavenom čase (voliteľné, per kanál)

Nastavenie pri modelke, **zvlášť pre Telegram a zvlášť pre Fanvue**, účinné len v Semi režime daného kanála. Hodnota je **počet minút** (nie fixne 15):

- **Nastavené číslo (napr. 15, 30, 60)** → ak sa `pending` nerozhodne do toľkých minút, worker odošle **prvý (AI-top) návrh** rovnakou send-cestou, ako keby ho vybral majiteľ. „Rozhodne ona, ktorý pošle" = poradie návrhov je rozhodnutie AI.
- **Vypnuté (prázdne / 0)** → `pending` čaká na rozhodnutie neobmedzene.

Klient si teda vie nastaviť napr. Telegram = po 15 min, Fanvue = nikdy (čaká vždy). Web pri zapnutí ponúkne rozumný predvyplnený default (15), ale je editovateľný. Odpočet stráži poller vo workeri (rovnaká kadencia ako `voice_jobs` poller / sweeper), takže beží aj keď je web aj Telegram zavretý.

## 7. Supersede pri novej správe (musí byť spoľahlivé)

Keď fanúšik napíše ďalšiu správu (alebo viac správ), kým je `pending` v stave `awaiting`, majiteľ nesmie schvaľovať zastarané návrhy. Postup:

1. Nová prichádzajúca správa sa uloží do histórie (ako dnes) a spustí debounce (`_schedule_reply`), takže viac správ za sebou sa spočíta do jednej dávky — nevznikne 5 kariet za 5 správ.
2. Pred vytvorením nového `pending` sa **atomicky uzavrú všetky otvorené `awaiting` pre danú konverzáciu** (`supersede_open(channel, conv_key)` → `awaiting` → `superseded`).
3. Control message starej karty sa upraví na „(neaktuálne — prišla nová správa)" a tlačidlá sa odstránia, nech na ňu majiteľ omylom neklikne.
4. AI vygeneruje nové návrhy z **aktuálneho** kontextu (vrátane nových správ) a pošle novú kartu.

Zabezpečenie proti race: `supersede_open` a `claim_pending_reply` bežia cez DB (atomický patch so `status='awaiting'` podmienkou), takže ani keď majiteľ klikne starú kartu presne vo chvíli príchodu novej správy, nemôže sa poslať zastaraná odpoveď — claim zlyhá, lebo riadok už nie je `awaiting`. Platí v oboch prípadoch (s aj bez časového fallbacku).

## 8. Dátový model

### 8.1 Per-kanálový režim (rozšírenie existujúcich tabuliek)

Režim je per kanál, preto žije pri každom kanáli zvlášť:

**Telegram → tabuľka `settings`:**
- `tg_reply_mode text not null default 'auto' check (tg_reply_mode in ('off','auto','semi'))`
- `tg_fallback_minutes integer` — počet minút do auto-odoslania; `NULL`/0 = vypnuté. `check (tg_fallback_minutes is null or tg_fallback_minutes > 0)`.
- `ai_paused` ostáva ako systémová núdzová pauza (flood) — nezávislá od `tg_reply_mode`.

**Fanvue → tabuľka `fanvue`** (co-located s `enabled`, tokenom):
- `reply_mode text not null default 'auto' check (reply_mode in ('off','auto','semi'))`
- `fallback_minutes integer` — to isté pre Fanvue; `NULL`/0 = vypnuté.
- `enabled` (pripojenie/beh agenta) ostáva; `reply_mode` riadi len správanie odpovedí. Supervisor beží pri pripojenom Fanvue; `reply_mode='semi'` musí bežať, aby vedel generovať návrhy.

Rozhodovanie workera **na každom kanáli nezávisle**:
- `auto` a (Telegram: nie `ai_paused`) → posielaj automaticky ako dnes.
- `semi` → schvaľovací tok.
- `off` → neposielaj na tomto kanáli nič.

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
                  -- awaiting → sent (manuálne alebo časový fallback) | skipped (Preskočiť)
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
- **nový modul `pending.py`**: `create_pending(...)`, `get_pending(id)`, `claim_pending(id)`, `supersede_open(channel, conv_key)`, `fallback_due()` — vráti `awaiting`, ktoré prekročili svoj per-kanálový `*_fallback_minutes` (Telegram: `settings.tg_fallback_minutes`, Fanvue: `fanvue.fallback_minutes`; `NULL` = nikdy).
- **`llm.py`**: nová metóda `suggest(system, history, n=3)` — jedno volanie, 3 varianty, parsované do zoznamu (zoradené od najlepšieho).
- **`userbot.py`**: v `_reply_locked` odbočka pri `settings.tg_reply_mode='semi'` — namiesto send bloku: `supersede_open` → `suggest` → `create_pending(channel='telegram')` → `control.notify` karta → `pending_reply=True` → return. Nový vstup `send_approved(pending, choice)` znovupoužije existujúci send blok (`send_message` + `add_message` + `_post_send_update`).
- **`fanvue_agent.py`**: rovnaká odbočka v `_reply` pri `fanvue.reply_mode='semi'`; send cez `Fanvue.send`, kontext cez `fv_messages`, `create_pending(channel='fanvue')`.
- **`control_bot.py`**: celé schvaľovacie UI — render karty, callbacky (výber návrhu, vlastná správa, foto-wizard, cena, hlasovka + jej preview), **oba per-kanálové režimy v hlavnom menu** (Telegram + Fanvue zvlášť), obnova `awaiting` po štarte repliky. Nové callback heady (napr. `ap:` approve-pick, `ac:` approve-custom, `af:` foto, `av:` voice, `rm:` reply-mode toggle s argumentom kanála).
- **poller** (nový `start_approval_poller` alebo napojenie na existujúci sweeper): odošle `awaiting` prekročené `fallback_due()` prvým návrhom.

### Web
- **Telegram sekcia modelky** (`/app/m/[id]/telegram/settings`): prepínač **Off / Auto / Semi** + pole **minúty do auto-odoslania** (prázdne = vypnuté) — zapisuje `settings.tg_reply_mode`, `settings.tg_fallback_minutes`.
- **Fanvue sekcia modelky** (`/app/m/[id]/fanvue/settings`): rovnaký prepínač + pole — zapisuje `fanvue.reply_mode`, `fanvue.fallback_minutes`. Nezávislé od Telegramu.
- Read helper na oba režimy (dnes sa číta `ai_paused` cez `getPausedMap`).
- Column-grant guard: nové stĺpce na `settings`/`fanvue` treba explicitne povoliť pre `authenticated` (migrácia 017 gotcha — table grant neexistuje, len po stĺpcoch).

## 10. Invarianty / čo sa nesmie pokaziť

- **Auto režim ostáva bajt-za-bajt ako dnes** — odbočka sa aktivuje len pri `…reply_mode='semi'` daného kanála.
- **Kanály sú nezávislé** — Telegram v Semi nesmie ovplyvniť Fanvue v Auto a naopak.
- **Každá odoslaná vec v Semi sa uloží ako `role='assistant'`** so správnym markerom a prebehne `_post_send_update` (clear `pending_reply`, `last_reply_at`, funnel, pamäť/summary) — inak by sa po návrate na Auto rozbila kontinuita persóny.
- **Vlastná (ručne napísaná) správa** sa ukladá rovnako → persóna sa z nej učí.
- **Flood a blokovaný fanúšik** sú tvrdé gates aj v Semi (chránia účet).
- **Idempotencia odoslania**: `claim_pending_reply` zaručí, že časový poller a manuálne kliknutie nemôžu poslať dvakrát.

## 11. Zámerne mimo v1 (YAGNI)

- Schvaľovanie na webe (len prepínač režimu; schvaľuje sa v Telegrame).
- Preview textových návrhov na webe.
- Telegram Stars / platené fotky na Telegrame (Telegram DM nemá paywall — platené len Fanvue).
- Iný počet návrhov než 3.
