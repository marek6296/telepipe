#!/usr/bin/env bash
#
# Nasadenie workera na Railway z čistého, commitnutého stromu.
#
# Prečo tento skript existuje: `railway up` nahráva ŽIVÝ pracovný adresár —
# teda aj rozpísané a necommitnuté súbory. 2026-08-18 takto do produkcie odišiel
# polorozpísaný src/fanvue_tenant.py (paralelná úprava už pridala volanie
# `await self._refresh_token_if_stale(row)`, ale definíciu metódy ešte nie) a
# zhodil Simone sync Fanvue vaultu, kým to nepresal redeploy z čistého checkoutu.
#
# Skript preto nahráva výhradne `git archive HEAD worker` — čo nie je
# commitnuté, do buildu sa nedostane (a __pycache__/ ani .venv/ tiež nie).
# A naopak: ak máš vo worker/ rozrobené zmeny, radšej sa vôbec nespustí, aby si
# nenasadil starú verziu v domnení, že nasadzuješ tú novú.
#
# Použitie:
#   worker/deploy.sh                 # bežný deploy
#   worker/deploy.sh --allow-dirty   # viem o rozrobených zmenách, nasaď HEAD aj tak

set -euo pipefail

PROJECT=telepipe
SERVICE=worker
ENVIRONMENT=production

usage() { sed -n '/^# Použitie:/,/allow-dirty/p' "$0" | cut -c3-; }

allow_dirty=0
case "${1:-}" in
  "")            ;;
  --allow-dirty) allow_dirty=1 ;;
  -h|--help)     usage; exit 0 ;;
  # Radšej nič nenasadiť, než nasadiť pri preklepe v argumente.
  *)             echo "✗ neznámy argument: $1" >&2; usage >&2; exit 2 ;;
esac

cd "$(git rev-parse --show-toplevel)"

dirty="$(git status --porcelain -- worker/)"
if [[ -n "$dirty" ]]; then
  echo "✗ worker/ nie je čistý — tieto zmeny NIE SÚ commitnuté a nenasadia sa:" >&2
  echo "$dirty" | sed 's/^/    /' >&2
  if (( allow_dirty )); then
    echo "  --allow-dirty: pokračujem, nasadzujem HEAD (bez týchto zmien)." >&2
  else
    echo "  Commitni ich, alebo spusti znova s --allow-dirty, ak je to zámer." >&2
    exit 1
  fi
fi

branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "$branch" == "main" ]] || echo "! pozor: nasadzuješ z vetvy '$branch', nie z main" >&2

commit="$(git log -1 --format='%h %s')"
echo "→ $SERVICE ($ENVIRONMENT) ← $commit"

staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
git archive HEAD worker | tar -x -C "$staging"

cd "$staging/worker"
railway link -p "$PROJECT" -s "$SERVICE" -e "$ENVIRONMENT"
railway up --service "$SERVICE" --ci --message "$commit"
