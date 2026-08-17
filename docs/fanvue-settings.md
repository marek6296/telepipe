# Fanvue — nastavenia agenta

> Telegram a Fanvue sú **dvaja agenti tej istej modelky**. Persona, fakty, pamäť
> a časová zóna sú spoločné (je to tá istá osoba a nesmie si protirečiť); tempo,
> otvorenosť, aktívne okno a celý predaj sú na každej platforme vlastné.
> Telegram číta `behavior`, Fanvue číta `fanvue`. Žiadny stĺpec nie je zdieľaný.

Zdroj: `/Users/marek/telegram/src/{fanvue_agent,fvflow,fvmedia,fvvoice}.py` (do
Telepipe portované bez jedinej zmeny — `diff` je prázdny), stará dashboard karta
`simona-dashboard/app/m/[model]/fanvue/{card,obsah}.tsx` a **živá schéma `tgai`**
starého projektu prečítaná cez PostgREST OpenAPI (defaulty nižšie sú jej,
znak po znaku).

---

## 1. `public.fanvue` — nastavenia Fanvue agenta

Migrácia 011 priniesla len pripojenie (OAuth + `connected`/`enabled`).
Migrácia **015** dopĺňa všetko, čo portovaný kód naozaj číta.

### Odpisovanie

| Stĺpec | Čo robí | Kde to worker číta | Default |
|---|---|---|---|
| `enabled` | Vypínač odpisovania. Vypnuté = udalosti sa vo fronte len kopia. | `fanvue_agent.tick()` (`settings["enabled"]`), `fanvue_tenant.start_fanvue()` | `false` |
| `greet_new` | Napíše prvá novému predplatiteľovi. | `fanvue_agent._dispatch()` → `_greet()` | `true` |
| `discovery_msgs` | Koľko prvých správ je „zoznamovanie" — vtedy sa nepredáva vôbec. Skončí skôr, keď sám povie, čo hľadá. | `fanvue_agent.phase()` | `4` |
| `summary_every` | Po koľkých správach prepíše priebežné zhrnutie chatu. | `fanvue_agent._remember()` | `12` |
| `heat` | Otvorenosť. `hot` pridá do promptu blok `fvflow.HOT` (ide naplno). | `fanvue_agent.build_prompt()` | `hot` |
| `extra_rules` | Voľný text do promptu — čím sa tu má líšiť od Telegramu. | `fanvue_agent.build_prompt()` | `''` |
| `reply_min_s` / `reply_max_s` | Náhodná pauza pred odoslaním odpovede. | `fanvue_agent._reply()` (`random.uniform`) | `20` / `180` |
| `active_start_min` / `active_end_min` | Okno hodín v jej miestnom čase (minúty od polnoci). Rovnaké hranice = odpisuje stále; okno smie prejsť cez polnoc. | `fanvue_agent.within_hours()` | `0` / `0` |

Časová zóna sa **nekopíruje** — berie sa `behavior.active_tz`
(`fanvue_agent.local_now()`), lebo je to vlastnosť tej osoby, nie platformy.

### Predaj a lievik

| Stĺpec | Čo robí | Kde to worker číta | Default |
|---|---|---|---|
| `sell_content` | Hlavný vypínač predaja. Vypnuté = neponúka nič a platená hlasovka nevznikne. | `fvflow.paid_moment()`, `fanvue_agent.may_offer()`, `fvvoice.should_speak()` | `true` |
| `offer_after_msgs` | Ponuka až po toľkých správach v chate. | `fvflow.paid_moment()`, `fanvue_agent.may_offer()` | `8` |
| `offer_cooldown_h` | Minimálny odstup medzi dvoma ponukami. | `fvflow.paid_moment()`, `fanvue_agent.may_offer()` | `12` |
| `nudge_after_msgs` | Po toľkých správach príde s ponukou **sama**, aj keď si nepýtal. `0` = nikdy. | `fvflow.paid_moment()` (vetva `nudge`) | `25` |
| `thank_purchases` | Poďakuje sa hneď po zaplatení, vlastnými slovami. | `fvflow.may_thank()` | `true` |
| `voices_enabled` | Smie vyrobiť hlasovku (ElevenLabs → upload do vaultu → príloha správy). | `fvvoice.should_speak()` | `false` |
| `voice_price_cents` | Cena **ostrej** hlasovky. Voľná ide vždy za 0. | `fanvue_agent._voice()` | `800` |

Tvrdé pravidlá, ktoré nastaviteľné nie sú (sú v kóde zámerne):
`fvflow.OFFER_REMINDER_H = 1` (neodomknutá ponuka blokuje ďalšiu),
`fvflow.VYHOVORKA_DNI = 5`, `fvflow.THANKS_DEDUP_S = 90`,
`fvflow.SLUB_HODIN = 14`, `fvvoice.COOLDOWN_H = 6`.

### Fotky a vault

| Stĺpec | Čo robí | Kde to worker číta | Default |
|---|---|---|---|
| `send_photos` | Smie k odpovedi priložiť fotku. | `fanvue_agent._pick_photo()` | `true` |
| `free_photo_max` | Koľko fotiek pošle zadarmo bez pýtania (zoznámenie). Potom už len na vyžiadanie. | `fvflow.free_photo_ok()`, `fvflow.guidance()` | `2` |
| `posting_enabled` | Sama pridáva príspevky na feed. | `fvmedia.due_to_post()` | `false` |
| `post_every_h` | Ako často. `0` = nikdy. | `fvmedia.due_to_post()` | `24` |
| `post_audience` | `subscribers` alebo `followers-and-subscribers`. | `fanvue_agent._post_to_feed()` | `followers-and-subscribers` |
| `last_post_at` | Kedy naposledy pridala. **Píše worker**, klient len číta. | `fvmedia.due_to_post()`, `_post_to_feed()` | `null` |
| `media_synced_at` | Kedy naposledy prebehla synchronizácia vaultu. **Píše worker.** | `fvvault.run_once()` | `null` |

### Čo sa zámerne NEPRENIESLO

`price_min_cents` (500) a `price_max_cents` (2500) sú v starej schéme aj na
starej karte, ale **žiadny riadok kódu ich nečíta** — cena je vlastnosťou
jednotlivej fotky (`fv_media.price_cents`) a hlasovky (`voice_price_cents`).
Mŕtvy stĺpec by len klamal, že niečo robí. `webhook_secret` v Telepipe nie je
per-modelku: appka na Fanvue je jedna spoločná a podpis overuje
`FANVUE_WEBHOOK_SECRET` z prostredia (`web/lib/env.ts`).

---

## 2. `public.fv_folders` — priečinky vaultu

| Stĺpec | Čo robí | Kde to worker číta | Default |
|---|---|---|---|
| `name` | Meno priečinka tak, ako je vo Fanvue. Nastavuje sa vo Fanvue, sem sa len sťahuje. | `fvvault.run_once()` | — |
| `role` | Na čo priečinok je: `sfw` (zadarmo), `nsfw` (za peniaze), `post` (na feed), `ignore` (nesiahne). | `fvmedia.role_of()` → `_pick_photo()`, `_post_to_feed()` | `ignore` |
| `price_cents` | Východisková cena pre **novo pribudnuté** fotky v tomto priečinku, keď k nim Fanvue nenavrhne vlastnú. | `fvvault.run_once()` | `0` |
| `media_count` | Koľko položiek priečinok mal pri poslednej synchronizácii. Píše worker. | `fvvault.run_once()` | `0` |

Nový priečinok pribudne ako `ignore`: nič sa nezačne posielať samo od seba.

## 3. `public.fv_media` — jednotlivé fotky

| Stĺpec | Čo robí | Kde to worker číta | Default |
|---|---|---|---|
| `media_uuid` | Id vo Fanvue. Do správy sa dá priložiť len médium, ktoré tam už existuje — vlastnú knižnicu si nedržíme. | všade | — |
| `folder` | Do ktorého priečinka patrí (rolu určuje priečinok). | `_pick_photo()`, `_post_to_feed()` | `''` |
| `kind` | `image` / `audio`. Zvuk sa ako fotka nikdy nepošle. | `fvmedia.pick()`, `next_post()` | `image` |
| `thumb_url` | Náhľad pre dashboard. Podpísaná adresa, prepisuje ju každá synchronizácia. | — (len UI) | `''` |
| `caption` | Čo je na fotke. **Podľa toho si ju vyberá** — slová z popisu sa porovnávajú s tým, o čom je práve reč. Fanvue popis navrhne samo. | `fvmedia.pick()` | `''` |
| `fits` | Druhé pole do tej istej zhody — kedy sa fotka hodí. | `fvmedia.pick()` | `''` |
| `price_cents` | Cena. **Bez ceny sa fotka z plateného priečinka neposiela vôbec** — poistka, aby platený obsah neodišiel zadarmo. | `fvmedia.pick(paid=True)`, `price_for()` | `0` |
| `active` | Vypnutá fotka sa neposiela ani nepridáva na feed. | `fvmedia.pick()`, `next_post()` | `true` |
| `spicy_override` | **Výslovné rozhodnutie o ostrosti tejto fotky** — prebíja rolu priečinka. `null` = nikto nerozhodol, platí priečinok. Toto prepína „Explicit" v dashboarde. | `fvmedia.effective_spicy()`, `_pick_photo()` | `null` |
| `spicy` | ODVODENÁ efektívna ostrosť: `coalesce(spicy_override, rola priečinka = 'nsfw')`. Drží ju trigger z migrácie 016; zápis do nej sa berie ako nastavenie `spicy_override`. | `fvmedia.pick()`, dashboard | odvodené |
| `sent_count` | Koľkokrát už odišla — medzi rovnako vhodnými vyhrá najmenej použitá. | `fvmedia.pick()` | `0` |
| `posted_at` | Kedy išla na feed. Na feed ide každá najviac raz. | `fvmedia.next_post()` | `null` |

`fv_media_sends` (komu už čo odišlo) ostáva výhradne service-role: je to
prevádzkový záznam workera a nikto ho ručne opravovať nemá.

---

## 4. Synchronizácia vaultu

**Stará služba ju nespúšťala vôbec.** `fvmedia.sync()` v predlohe existuje, ale
nevolá ju ani `fanvue_agent.tick()`, ani `main_fanvue.py` — jediným spúšťačom
bolo tlačidlo „načítať z vaultu" v dashboarde, ktorý si celú synchronizáciu
robil sám v Next.js (`syncFanvueVault` → `lib/data.syncVault`). V Telepipe to
takto ísť nemôže: prístupový token je šifrovaný a web ho do rúk nedostane.

Preto **fronta**:

```
web (server action)  →  fanvue_sync_requests  →  worker (fvvault.VaultSync)
                                              →  fv_folders / fv_media
                                              →  fanvue.media_synced_at
```

* `fanvue_sync_requests` má partial unique index na `(model_id) where finished_at is null`
  — jedna čakajúca požiadavka na modelku, dvojklik nevyrobí frontu.
* Server action pred vložením „vyprší" požiadavky staršie než 15 minút, aby
  vypnutý worker nezablokoval tlačidlo navždy.
* `fvvault.VaultSync` beží ako samostatná úloha vedľa agenta a štartuje pri
  `fanvue.connected` — teda **aj keď je odpisovanie vypnuté**. Priradiť
  priečinkom rolu musí ísť skôr, než sa agent zapne.
* Synchronizácia **nikdy neprepíše naše stĺpce** existujúcej fotky
  (`caption`, `fits`, `price_cents`, `active`, `spicy_override`, `sent_count`,
  `posted_at`). Osviežuje len `folder`, `kind` a `thumb_url` — a keď sa fotka
  presunie do iného priečinka, trigger z 016 jej dopočíta novú efektívnu
  `spicy` (fotky s vlastným `spicy_override` sa nemenia).
* Dobehnuté požiadavky staršie než 24 h `VaultSync` **maže** (raz za hodinu).
  Fronta je krátkodobá pracovná pamäť — dashboard z nej číta výsledok
  posledného kliku a nič staršie.
