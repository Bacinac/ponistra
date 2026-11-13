#!/usr/bin/env bash
# The public demo: the release's own frontend over the answers the real backend gave, recorded
# from a made-up company (help_seed) in a stack of the gate's own, built in demo mode (frontend/demo),
# walked in a browser without a network that fails on anything the demo cannot answer by itself,
# and gated file by file before it leaves. Nothing leaves this machine without --deploy.
#
#   scripts/demo.sh            record into frontend/demo/recorded, build, walk and gate into .git/ponistra-check/demo
#   scripts/demo.sh --shots    also retake docs/screenshots from the walked demo
#   scripts/demo.sh --deploy   also publish it to the Cloudflare Pages project ponistra-demo
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

DEPLOY=0
SHOTS=0
for arg in "$@"; do
  case "$arg" in
  --deploy) DEPLOY=1 ;;
  --shots) SHOTS=1 ;;
  -h | --help)
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *)
    echo "unknown option: $arg" >&2
    exit 2
    ;;
  esac
done

PROJECT=ponistra-demo
DOMAIN=${PONISTRA_DEMO_DOMAIN:-demo-ponistra.boskovic.biz}
RECORDED=frontend/demo/recorded
CREDITS=backend/apps/help/media/credits.json
SCREENSHOTS=docs/screenshots
# The tour's frames, in the order a visitor would go.
TOUR=(documents text table slides mail calendar)

GATE=$(git config --get publicgate.command) || {
  echo "no publicgate.command in this clone; the demo is not built unchecked" >&2
  exit 1
}
[[ -x $GATE ]] || {
  echo "publicgate.command $GATE is not an executable" >&2
  exit 1
}
if [[ $DEPLOY == 1 ]]; then
  # The one token every public site of boskovic.biz deploys with (web/README.md).
  TOKEN_FILE=${PONISTRA_CF_TOKEN_FILE:-/mnt/docker/web/.cf-token}
  [[ -s $TOKEN_FILE ]] || {
    echo "Cloudflare token missing: $TOKEN_FILE" >&2
    exit 1
  }
fi

store="$(cd "$(git rev-parse --git-common-dir)" && pwd)/ponistra-check"
OUT="$store/demo"
mkdir -p "$store"
run=$(mktemp -d "$store/demo.XXXXXX")
# The browser writes as a user of its own into folders made here, which this script can remove.
mkdir -p "$run"/recorded/{blobs,collab,grids} "$run/shots"
chmod -R 777 "$run"
export PONISTRA_RUN="$run"
export COMPOSE_FILE="compose.yaml:compose.override.yaml:$PWD/compose.check.yml:$PWD/e2e/demo/compose.demo.yml"
COMPOSE_PROJECT_NAME="ponistra-demo-$(basename "$PWD")"
export COMPOSE_PROJECT_NAME
guard=
down() {
  docker compose --profile check down --volumes --remove-orphans --timeout 5 >/dev/null 2>&1 || true
}
finish() {
  [[ -z $guard ]] || kill "$guard" 2>/dev/null || true
  down
  rm -rf "$run"
}
trap finish EXIT
trap 'exit 130' INT TERM

# LXC 210 has no swap (scripts/check.sh): the stack goes before the container does.
(
  while sleep 5; do
    left=$(awk '/^MemAvailable:/ { print int($2 / 1024) }' /proc/meminfo)
    if [[ $left -lt 3000 ]]; then
      echo "demo: $left MB of memory left; the stack is stopped" >&2
      docker compose --profile check kill >/dev/null 2>&1
      exit
    fi
  done
) &
guard=$!

echo "demo: recording"
mkdir -p frontend/node_modules
if ! docker compose up -d --wait --quiet-pull backend frontend; then
  for stopped in $(docker compose ps -a --status exited --format '{{.Service}}'); do
    docker compose logs --no-color --tail=80 "$stopped" >&2
  done
  exit 1
fi
sessions=$(docker compose exec -T backend python manage.py help_seed)
# A new document's own state, which the server writes as it makes one (apps/documents/views.py).
docker compose exec -T backend python manage.py shell -v 0 -c \
  'import sys; from apps.content import styles; sys.stdout.buffer.write(styles.template())' \
  >"$run/recorded/template.bin"
docker compose exec -T backend python -c 'import sys, pycrdt; pycrdt.Doc().apply_update(sys.stdin.buffer.read())' \
  <"$run/recorded/template.bin" || {
  echo "demo: the template for a new document is not a Yjs update" >&2
  exit 1
}
docker compose build -q e2e
docker compose run --rm --no-deps -T -v "$PWD/e2e/demo:/e2e/demo:ro" -v "$run:/demo" \
  -e PONISTRA_DEMO="$sessions" e2e node_modules/.bin/playwright test --config demo/demo.config.ts record.spec.ts

if [[ -f $CREDITS ]]; then
  credits=$(jq -c 'map(del(.file))' "$CREDITS")
elif [[ -d $(dirname "$CREDITS") ]]; then
  echo "demo: $(dirname "$CREDITS") holds media but no $(basename "$CREDITS")" >&2
  exit 1
else
  credits='[]'
fi
jq -c --argjson credits "$credits" '. + {credits: $credits}' "$run/recorded/meta.json" >"$run/meta.json"
mv "$run/meta.json" "$run/recorded/meta.json"
rm -rf "$RECORDED"
cp -r "$run/recorded" "$RECORDED"
echo "demo: recorded $(wc -l <"$run/pages.txt") pages into $RECORDED"

echo "demo: building"
rm -rf "$OUT"
mkdir -p "$OUT"
docker compose run --rm --no-deps -T -e NODE_ENV=production -v "$PWD/frontend/demo:/app/demo:ro" -v "$OUT:/out" \
  --entrypoint sh frontend -c 'sh packages.sh && npx vite build --mode demo --outDir /out --emptyOutDir'
down
# The build keeps its source maps beside it (sourcemap: hidden); the repository is not public.
find "$OUT" -name '*.map' -delete

# Without a network: whatever the demo would ask a server for fails the walk.
browse() {
  docker run --rm --network none --shm-size 1g --user pwuser -v "$PWD/e2e/demo:/e2e/demo:ro" \
    -v "$OUT:/site:ro" -v "$run:/demo" "$@" ponistra/e2e \
    node_modules/.bin/playwright test --config demo/demo.config.ts "${spec:?}"
}
echo "demo: walking"
spec=walk.spec.ts browse

if [[ $SHOTS == 1 ]]; then
  echo "demo: pictures"
  spec=shots.spec.ts browse -v "$run/shots:/shots"
  # libwebp's own tools (BSD), as the browser encodes no animation.
  docker run --rm -v "$run/shots:/shots" -w /shots -e OWNER="$(id -u):$(id -g)" alpine:3.22 sh -euc '
    apk add --no-cache -q libwebp-tools
    frames=""
    for each in "$@"; do
      cwebp -quiet -q 82 "$each.png" -o "$each.webp"
      frames="$frames -d 2500 $each.png"
    done
    # shellcheck disable=SC2086
    img2webp -loop 0 -lossy -q 75 $frames -o tour.webp
    chown "$OWNER" ./*.webp' sh "${TOUR[@]}"
  mkdir -p "$SCREENSHOTS"
  for each in "${TOUR[@]}" tour; do cp "$run/shots/$each.webp" "$SCREENSHOTS/"; done
  cp "$run/shots/social-preview.png" "$SCREENSHOTS/"
  echo "demo: pictures in $SCREENSHOTS"
fi

echo "demo: gating"
find "$OUT" -type f -print0 | xargs -0 "$GATE" scan --files
[[ $SHOTS == 0 ]] || find "$SCREENSHOTS" -type f -print0 | xargs -0 "$GATE" scan --files

[[ $DEPLOY == 1 ]] || {
  echo "demo: built, walked and gated -> $OUT"
  exit 0
}

echo "demo: publishing"
CLOUDFLARE_API_TOKEN=$(tr -d ' \n\r\t' <"$TOKEN_FILE")
CLOUDFLARE_ACCOUNT_ID=${CLOUDFLARE_ACCOUNT_ID:-3e7a41dadfd065fac67c6922c3f3b43e}
export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID
pages="https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects"
cloudflare() {
  curl -fsS -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'Content-Type: application/json' "$@"
}
if ! cloudflare "$pages/$PROJECT" >/dev/null 2>&1; then
  cloudflare -X POST "$pages" -d "{\"name\": \"$PROJECT\", \"production_branch\": \"main\"}" >/dev/null
fi
docker run --rm -v "$OUT:/site:ro" -e CLOUDFLARE_API_TOKEN -e CLOUDFLARE_ACCOUNT_ID -e NPM_CONFIG_UPDATE_NOTIFIER=false \
  node:26-alpine npx -y wrangler@latest pages deploy /site --project-name "$PROJECT" --branch main
if ! cloudflare "$pages/$PROJECT/domains/$DOMAIN" >/dev/null 2>&1; then
  cloudflare -X POST "$pages/$PROJECT/domains" -d "{\"name\": \"$DOMAIN\"}" >/dev/null
fi
status=$(cloudflare "$pages/$PROJECT/domains/$DOMAIN" | jq -r '.result.status')
echo "demo: published to https://$DOMAIN ($status)"
[[ $status == active ]] || echo "demo: $DOMAIN is $status; its CNAME to $PROJECT.pages.dev has to be in the zone" >&2
