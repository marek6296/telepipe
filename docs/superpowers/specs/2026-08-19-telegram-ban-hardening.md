# Ochrana Telegram účtov — zaplátanie dier

**Dátum:** 2026-08-19
**Stav:** pripravené, ČAKÁ na commit paralelnej session (kolízia v `worker/src/`)
**Podklad:** audit z 2026-08-19 (read-only)

## Prečo tento dokument existuje a nie rovno kód

Paralelná session mala v čase písania rozrobených +326 riadkov práve v
`db.py`, `registry.py`, `userbot.py`, `runner.py` a `config.py` — necommitnutých.
Písať do tých istých súborov znamená riskovať tichú stratu práce (v tomto repo
sa to už raz stalo). Opravy sú preto pripravené sem a nasadia sa, keď bude strom
čistý.

## Východisko

Ochrana **existuje a je slušná**: 40 odpovedí/hod, 5 súbežných chatov,
6 oslovení/hod, aktívne okno ~14 h, ľudské oneskorenia s pauzami, oslovenie
každého človeka najviac raz za život, `PeerFloodError` → 24 h pauza.

Problém nie je v tom, že by ochrana chýbala. Problém je, že sa na štyroch
miestach **dá obísť bez toho, aby si to niekto všimol**.

---

## 1. `ai_paused` sa maže prepnutím režimu odpovedania

**Kde:** `worker/src/db.py`, `set_tg_reply_mode()` — pri `auto`/`semi` zapisuje
`ai_paused = False`.

**Prečo je to zlé:** `PeerFloodError` je najvážnejší signál, aký Telegram dá.
Reakcia je 24 h pauza zapísaná do `settings.ai_paused`. Keď majiteľ v control
bote klikne na režim odpovedania, pauza sa ticho zruší — bez varovania a bez
informácie, koľko z tých 24 h ešte malo bežať. Účet sa rozbehne priamo do
spam-flagu.

**Oprava:** rozdeliť dve významovo odlišné pauzy.

- Zaviesť `settings.flood_until timestamptz` (nová migrácia). Pri
  `PeerFloodError` sa zapíše `now() + 24h` **sem**, nie do `ai_paused`.
- `ai_paused` ostane tým, čím bol: ručná pauza majiteľa. Tú smie prepnutie
  režimu zrušiť ďalej — to je v poriadku a je to zaužívané.
- Gate v `userbot.py` (`_reply_locked` ~427, sweep ~2167) kontroluje **obe**:
  `ai_paused OR flood_until > now()`.
- `set_tg_reply_mode` sa `flood_until` **nedotkne**.
- Control bot ukáže zvyšný čas („Flood pause: 18 h left") a odomknúť ho smie iba
  vedomé tlačidlo, nie vedľajší účinok.

**Test:** prepnutie režimu počas flood pauzy ju NESMIE skrátiť.

---

## 2. Tri cesty odosielania prehltnú flood chybu

**Kde:** `worker/src/userbot.py` — `_send_photo` (~1450), `_send_voice` (~1820),
`_send_generated_voice` (~1627). Všetky majú `except Exception` + `log.warning`.
`_send_generated_voice` navyše po zlyhaní **hneď skúsi `send_message` na ten
istý účet** — teda okamžitý opakovaný pokus možno práve do floodu.

**Prečo je to zlé:** 24 h ochrana z bodu 1 sa spustí len z textovej cesty. Fotka
alebo hlasovka do floodu tú ochranu nespustí vôbec.

**Oprava:**

- V každom z tých troch `except` blokov najprv `await self._note_flood(exc)`
  (rovnako ako to robí textová cesta na ~1104), až potom `log.warning`.
- V `_send_generated_voice` **zrušiť okamžitý fallback na `send_message`**, ak
  bola chyba flood/`PeerFloodError`. Pri inej chybe (napr. chybný súbor) fallback
  ostáva — tam dáva zmysel.

**Test:** `_send_photo` aj `_send_voice` s vyhodeným `PeerFloodError` musia
nastaviť flood pauzu; generovaná hlasovka nesmie po floode skúsiť text.

---

## 3. Malé floody sú neviditeľné

**Kde:** `worker/src/runner.py` ~203–206, konštrukcia `TelegramClient`.
Telethon má `flood_sleep_threshold = 60` (default) a nikde sa neprepisuje.

**Prečo je to zlé:** každý `FloodWaitError` do 60 s si Telethon sám odspí
a zopakuje. Do našich logov, do `_flood_until` ani k majiteľovi sa nedostane nič.
Pritom drobné floody sú **včasné varovanie** pred tým veľkým — a my ho nemáme.

**Oprava:**

- `TelegramClient(..., flood_sleep_threshold=0)` — každý FloodWait tak vyletí ako
  výnimka a prejde našou logikou.
- V `limity.py` upraviť prah hlásenia: majiteľa neotravovať pod 300 s (ostáva),
  ale **vždy zalogovať na WARNING** a započítať do počítadla.
- Pridať jednoduché počítadlo „koľko FloodWaitov za poslednú hodinu"; nad prahom
  (napr. 3) sa modelka sama spomalí — zdvojnásobí `factor` — a upozorní majiteľa.

**Pozor:** `flood_sleep_threshold=0` znamená, že aj 5-sekundový FloodWait teraz
vyletí. Kód, ktorý ho doteraz nevidel, ho musí zniesť. Preto to ide spolu
s bodom 2 a nie skôr.

---

## 4. Žiadny denný strop

**Kde:** existuje len `max_replies_per_hour`.

**Prečo je to zlé:** 40/hod × 14 h okna = **až 560 odpovedí denne** na jeden
Telegram účet. Hodinový limit tomu nebráni, lebo sa počíta v kĺzavom okne.

**Oprava:**

- `behavior.max_replies_per_day` (default **200**) a
  `behavior.max_new_people_per_day` (default **20**), obe klientsky editovateľné.
- Počítať z DB za posledných 24 h (nie kalendárny deň — reset o polnoci by robil
  nárazy).
- Gate vedľa hodinového v `_rate_ok`.

---

## 5. Limity zlyhávajú OTVORENE

**Kde:** `userbot.py` `_oslovenych_za_hodinu` (~2012) a `_aktivne_rozhovory`
(~2025) pri chybe Supabase vrátia prázdnu množinu → limit sa **vypne**.
`_rate_left` spadne na pamäťové počítadlo, ktoré je po deploy prázdne.

**Prečo je to zlé:** ochrana je najslabšia presne vtedy, keď je najviac pohybu
(výpadok DB počas deployu). `_link_quota_ok` to má správne — zlyháva zatvorene.

**Oprava:** pri chybe DB vrátiť „limit vyčerpaný", nie „limit neexistuje".
Radšej chvíľu neodpisovať než odpisovať bez brzdy.

---

## 6. Flood pauza neprežije reštart

**Kde:** `userbot.py` `_flood_until` je iba pole v pamäti (~138).

**Oprava:** vyriešené automaticky bodom 1 — `settings.flood_until` je v DB.
Pamäťové pole ostane ako rýchla cache.

---

## 7. Nový účet ide naplno od prvej sekundy

**Oprava:** `models.tg_connected_at` (nová migrácia, backfill na `created_at`).
Rozbehová krivka na hodinový aj denný strop:

| Vek účtu | Podiel limitu |
|---|---|
| < 24 h | 25 % |
| 1–3 dni | 50 % |
| 3–7 dní | 75 % |
| > 7 dní | 100 % |

Navyše `Reconciler` pri prvom štarte účtu mladšieho než 24 h stiahne 15 dialógov
namiesto 60.

---

## 8. Bez rozostupu pri štarte repliky

**Kde:** `main.py` `Pool.tick` (~145–182) spustí až 25 Telethon `connect()`
v jednej iterácii z jednej IP.

**Oprava:** `await asyncio.sleep(uniform(2, 6))` medzi štartmi tenantov.
Pri 25 účtoch to znamená rozbeh cez ~1–2 minúty namiesto naraz.

---

## 9. Nula znamená raz „bez limitu" a raz „úplné ticho"

**Kde:** `max_active_chats = 0` a `max_outreach_per_hour = 0` = bez limitu, ale
`max_replies_per_hour = 0` = **účet onemie navždy**. Obe sú klientsky
editovateľné tlačidlá v control bote.

**Oprava:** zjednotiť na „0 = bez limitu" a spodnú hranicu pre odpovede riešiť
minimom (napr. 1). Plus veta v control bote, čo nula robí.

---

## Poradie nasadenia

1. **1 + 2 spolu** — tiché zabijaci: ochrana existuje, ale sa obíde.
2. **3** — až po 2, lebo odkryje výnimky, ktoré kód doteraz nevidel.
3. **5** — malá zmena, veľký efekt.
4. **4** — vyžaduje migráciu a UI.
5. **7, 8, 9, 6** — postupne.

Každý bod = vlastný commit + testy. Worker má ~1600 testov, musia ostať zelené.
Nasadenie `worker/deploy.sh` až po dohode — deployuje HEAD, čiže aj prácu
paralelnej session.
