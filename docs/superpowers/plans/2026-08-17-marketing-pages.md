# Marketing stránky — Features / How it works / Pricing

Marek: „na hlavnej stránke keď scrolujeme tam nechcem mať tie karty čo sú v menu —
tieto 3 nebudú na hlavnej stránke, budú mať samostatné stránky, že sa preklikneme,
nie že scrolujeme dole. A urob ich pekne do nášho štýlu, žiadne AI slop veci."

## Rozsah

| Stránka | Čo tam ide |
|---|---|
| `/` (landing) | LEN: intro text → kinematická scéna s telefónom → CTA → footer. Sekcie features / how it works / pricing sa ODSTRÁNIA. |
| `/features` | Karty s animovaným shader pozadím (predloha: `@paper-design/shaders-react` Warp), monochróm |
| `/how-it-works` | GSAP SVG clip-path interakcia (predloha: hover na položku vľavo → vpravo sa preskladá obrázok cez clip-path masky) |
| `/pricing` | 3 balíky + monthly/yearly prepínač s animovanými číslami (NumberFlow) |

## Balíky (finálne ceny od Mareka)

| Balík | Mesačne | Ročne (−20 %, zaokrúhlené) |
|---|---|---|
| Free | $0 | $0 |
| Pro | $14.99 | $143.90 |
| Enterprise | $49.99 | $479.90 |

Obsah balíkov sa odvodí od reálnych schopností produktu (počet modeliek, Telegram/Fanvue
agent, hlasovky, kredity, podpora) — nevymýšľať funkcie, ktoré neexistujú.

## Pravidlá

- Monochróm ako zvyšok webu (landing paleta `landing.css`), zlatá LEN v logu a v telefóne na `/`.
- Shader karty na `/features`: predloha má farebné HSL palety → u nás odtiene bielej/šedej.
- Žiadne emoji ikonky, len tenké lucide.
- Nav (Features / How it works / Pricing) → `<Link>` na stránky, nie `#kotvy`. Aktívna položka zvýraznená.
- Spoločný marketing layout: nav + footer zdieľané medzi `/`, `/features`, `/how-it-works`, `/pricing`.
- `prefers-reduced-motion`: statické varianty všade.
- Obrázky na `/how-it-works` zatiaľ mockupy (placeholder), doriešime neskôr.

## Realizácia (odchýlky od plánu)

| Vec | Ako to nakoniec je |
|---|---|
| Layout | Route group `web/app/(marketing)/` — layout drží nav + footer pre všetky štyri stránky. `LandingNav` si variant určuje sám z `usePathname()`: na `/` ostáva `data-nav-reveal` (GSAP intro), inde je to bežná fixná hlavička s aktívnou položkou. Žiadny duplicitný markup. |
| Middleware | `web/lib/supabase/middleware.ts` mal whitelist len `/`, `/login`, … — nové stránky by neprihláseného presmerovali na `/login`. Pridané `/features`, `/how-it-works`, `/pricing`. |
| Shader karty | Dáta aj presety žijú v client komponente `components/marketing/feature-grid.tsx` — lucide ikona sa nedá poslať zo server komponentu do client komponentu (Next 16 to odmietne pri prerenderi). |
| Shader výkon | `next/dynamic({ssr:false})` + IntersectionObserver (mount 240 px pred viewportom, potom už namontovaný ostáva) + `maxPixelCount` 480² + `minPixelRatio 1`. Na mobile (`max-width:767px` / `pointer:coarse`) a pri `prefers-reduced-motion` sa WebGL nepúšťa vôbec — beží statický gradient z tej istej palety. Knižnica má navyše vlastný `visibilitychange` + IO pause. |
| Mobil na `/how-it-works` | Sticky vizuál sa v grid layoute na mobile nedá (sticky grid item je ohraničený vlastnou grid area), takže po klepnutí na krok sa vizuál doscrolluje (`scrollIntoView`, na desktope sa nedeje nič). |
| Placeholder obrázky | `web/public/how-it-works/0{1,2,3}-*.svg` — vlastné neutrálne SVG mockupy (telefón s kódom, setup obrazovka, chat + graf). Žiadny externý host. |
