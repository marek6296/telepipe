# Chat — Community, Community+ a DM na admina

**Dátum:** 2026-08-19
**Vrstva:** 3 z 3 (gating ✅ → notifikácie ✅ → **chat**)

## Čo staviame

Facebook-ovský chat: **bublina vľavo dole**, klik otvorí zoznam kanálov, klik na
kanál otvorí okno — a okná stoja **vedľa seba na spodnej lište**. Správy
pribúdajú s animáciou (pruženie bubliny, typing indikátor, plynulý scroll),
v našich `--app-*` farbách. Žiadne indigo/violet gradienty z referencie.

### Tri druhy miestností

| `kind` | Kto vidí | Kto píše |
|---|---|---|
| `community` | **všetci** vrátane zamknutých | všetci okrem umlčaných |
| `community_plus` | len odomknutí (`account_unlocked()`) | tí istí |
| `admin_dm` | jej majiteľ + **všetci admini** | tí istí |

`community` a `community_plus` sú **po jednej** (partial unique index).
`admin_dm` vzniká na požiadanie, jedna na účet — takže „napíš Marekovi" má každý
človek svoju.

Prístup rozhoduje **jedna funkcia** `chat_room_visible(room, account)`, ktorá
stojí na `account_unlocked()` z vrstvy 1. Nechceme druhé miesto, kde sa
rozhoduje o odomknutí.

### Fotky

**Len v `admin_dm`.** Vo verejných kanáloch by ich mohol nahrať aj neschválený
účet a Marek by ich musel moderovať. Bucket `chat`, cesta
`dm/<owner_account_id>/<uuid>`, prísne privátny — obrázok sa servíruje cez
signed URL, nikdy verejným linkom.

RLS na `chat_messages` INSERT to vynúti aj v databáze: `image_path` smie byť
neprázdny **iba** keď je miestnosť `admin_dm`. UI nie je hranica.

### Moderácia

- **Admin zmaže hocikomu správu** — soft delete (`deleted_at`, `deleted_by`),
  v okne ostane „Message removed". Tvrdé mazanie by rozbilo poradie a znemožnilo
  dohľadať, čo sa stalo.
- **Admin umlčí človeka** — `chat_mutes`. Umlčaný ďalej **číta**, ale
  `chat_can_post()` ho nepustí písať. Rieši spamera bez toho, aby prišiel
  o prístup do produktu.
- **Bežný človek si vlastnú správu zmazať nevie** (Marekova voľba).

### Notifikácie

- Nová DM správa od klienta → **Telegram** do Marekovho súkromného bota
  ([[TelePipe Admin Bot]]) + zvonček. Odosiela to web pri zápise správy, nie
  trigger: trigger v Postgrese nevie robiť HTTP.
- Nová správa v miestnosti, ktorú mám otvorenú, notifikáciu **nerobí** — vidím ju.
- Neprečítané drží `chat_reads (room_id, account_id, last_read_at)`.

## Dátový model

```
chat_rooms      id, kind, owner_account_id, created_at
chat_messages   id, room_id, sender_id, body, image_path,
                deleted_at, deleted_by, created_at
chat_reads      room_id, account_id, last_read_at        (pk: room_id, account_id)
chat_mutes      account_id pk, muted_by, reason, created_at
```

Funkcie: `account_is_admin(uuid)`, `chat_room_visible(uuid, uuid)`,
`chat_can_post(uuid, uuid)`, `my_dm_room()` (vráti/založí moju DM),
`admin_delete_chat_message(uuid)`, `admin_set_chat_mute(uuid, boolean, text)`,
`admin_list_dm_rooms()`.

Realtime: `chat_messages` do publikácie `supabase_realtime`.

## Web

- `web/components/chat/chat-dock.tsx` — bublina vľavo dole + zoznam kanálov
- `web/components/chat/chat-window.tsx` — jedno okno (hlavička, správy, input)
- `web/components/chat/message-bubble.tsx` — animovaná bublina
- `web/components/chat/chat-provider.tsx` — ktoré okná sú otvorené (localStorage)
- `web/lib/chat.ts` (server) + `web/lib/chat-ui.ts` (client-safe typy)
- `web/app/api/chat/upload/route.ts` — fotka do bucketu + signed URL
- Dock sa mountuje v `/app` **aj** na `/locked` — zamknutý má mať Community
  a DM na Mareka.

## Čo ZÁMERNE nerobíme

- vlákna, reakcie, úpravy správ, čítacie potvrdenia po jednotlivých ľuďoch
- odpisovanie na DM priamo z Telegramu (zatiaľ len upozornenie; odpisuje sa vo webe)
- vyhľadávanie v histórii
