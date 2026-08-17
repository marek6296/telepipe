# Telepipe app redesign — Efferd monochróm (invertovaný)

> Referencia: Efferd dashboard screenshot + AppShell/Dashboard template štruktúra.
> Marekove slová: „žiadne AI slop ikonky, čistý profi dizajn, nie veľa farieb,
> presne ako obrázok, len invertované — čierne pozadie, biele prvky."

## Zásady

- **Monochróm:** pozadie #0A0A0A/#000, povrchy #111–#161616, borders #262626,
  text biela/#A1A1AA. ŽIADNE zlaté buttony, žiadne farebné chip-y, žiadne
  gradientové ikonky.
- **Farba len ako signál:** zelená/červená výhradne pre delta percentá
  (▲ 3.1% vs last week) a status bodky (active zelená, error červená) —
  malé, tlmené, presne ako referencia.
- Zlatá: LEN logo. Nikde inde v app.
- **Typografia nesie hierarchiu:** veľké čisté čísla (stat tiles ako referencia:
  label hore, veľké číslo, malá delta pod tým), sekcie oddelené whitespace,
  nie boxami vo farbe.
- **Sidebar ako Efferd:** skupiny s malými šedými nadpismi (PRODUCT/WORKSPACE
  vzor → naše: MODELS / ACCOUNT / ADMIN), tenké lucide ikony 16px monochróm,
  aktívna položka = jemné svetlé pozadie (#1A1A1A), nie zlatý akcent.
  Dole changelog-style karta voliteľne, Help/Docs pattern, © Telepipe.
- **Grafy:** monochróm — bary s jemným vertikálnym gradientom (biela→transparent
  ako referencia inverzne), stepped line pre druhý graf, žiadne farebné série;
  legenda textová.
- **Buttony:** primárny = biely button s čiernym textom (inverzia Efferd čierneho),
  sekundárny = ghost s borderom. Žiadne tieňové „tactile" efekty v app
  (tie ostávajú len na landing/auth).
- **Tabuľky:** čisté riadky, tenké deliace čiary, žiadne zebra farby.
- Landing (/) a auth stránky sa NEMENIA.

## Rozsah

Všetko pod /app: shell + sidebar, dashboard (stat tiles + 2 grafy štýlom
referencie: Net spend / Messages by model), models list, model detail taby
(telegram wizard, fanvue, persona, behavior, photos, chats, usage), account,
admin sekcia (dashboard, users, models, usage). Konzistentne, žiadna stránka
nesmie ostať v starom zlatom štýle.
