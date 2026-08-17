# web/ — Telepipe (fáza 2)

Next.js App Router aplikácia: marketingová landing (GSAP cinematic hero),
Supabase Auth (email+heslo), Telegram connect wizard a klientská app na správu
modeliek. Spec: `docs/superpowers/specs/2026-08-17-telepipe-phase2-web-design.md`,
plán: `docs/superpowers/plans/2026-08-17-phase2-web.md`.

## Stack

- Next.js 16 (App Router, Turbopack) + TypeScript
- Tailwind CSS v4 (téma v `app/globals.css`, žiadny `tailwind.config`)
- GSAP + ScrollTrigger (landing), Framer Motion (app), lucide-react
- `@supabase/ssr` + `@supabase/supabase-js`
- shadcn štruktúra v `components/ui`

## Vývoj

```bash
cp .env.example .env.local   # doplň kľúče z root .env
npm install
npm run dev                  # http://localhost:3000
npm run build                # musí prejsť pred každým commitom
npx tsc --noEmit             # typecheck
```

## Téma

Čierne pozadie, zlaté akcenty (`--gold #D4AF37`), biele logo, Poppins.
Znovupoužiteľné triedy v `app/globals.css`: `btn-modern-light` / `btn-modern-dark`
(tactile buttony), `glass-panel` / `glass-input`, `premium-depth-card`,
`widget-depth`, `bg-grid`, `film-grain-fixed`, `animate-element` + `animate-delay-*`.
Celá téma rešpektuje `prefers-reduced-motion`.

## Env premenné

Viď `.env.example`. `ENCRYPTION_KEY` musí byť identický s workerom (Railway),
inak worker nedešifruje Telegram session zapísané webom.
