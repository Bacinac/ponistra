#!/usr/bin/env sh
# The gate: lint, types and tests in a stack of its own (compose.check.yml), started from the dev
# images (PONISTRA_TARGET=dev) and thrown away after. No CI exists; this is it.
#
#   scripts/check.sh            what a push waits for: the static checks of the side it touched and
#                               the pytest and vitest tests that ran the functions it changed since a
#                               tree they passed on, as the full runs noted them (scripts/select.py);
#                               nothing for a tree that passed them, in whichever worktree
#   scripts/check.sh --browser  the browser's tests the change since the last tree they passed on
#                               reaches; run after each push by scripts/check-full.sh --browser
#   scripts/check.sh --full     everything, noting those files anew and what failed in
#                               .git/ponistra-check/failed.json, and the help's pictures; each night
#   scripts/check.sh --shots [name]  only the help's pictures, or those whose name holds `name`
#
# A run that cannot choose (nothing noted or passed yet, a change every test stands on) runs every
# test of its kind. The outcomes of the last two kinds are kept, a line a tree, in
# .git/ponistra-check/full and browser; a push names those that failed. The trees a push's checks
# passed on are kept in .git/ponistra-check/passed, the fingerprints Excel's corpus passed on in
# corpus, and how long each phase took in <mode>.log.
set -eu
cd "$(git rev-parse --show-toplevel)"

mode=${1:-}
mode=${mode#--}
case $mode in
"") mode=push ;;
browser | full | shots) ;;
*)
  echo "usage: scripts/check.sh [--browser | --full | --shots [name]]" >&2
  exit 2
  ;;
esac

store="$(cd "$(git rev-parse --git-common-dir)" && pwd)/ponistra-check"
mkdir -p "$store"
# The stack is named after the tree: two checks of one tree would take each other's containers.
exec 9>"$store/tree-$(basename "$PWD").lock"
flock -n 9 || {
  echo "check: another check of this tree is running; waiting for it" >&2
  flock 9
}
run=$(mktemp -d "$store/run.XXXXXX")
export PONISTRA_RUN="$run"
COMPOSE_FILE="${COMPOSE_FILE:-compose.yaml:compose.override.yaml}:$PWD/compose.check.yml"
COMPOSE_PROJECT_NAME="ponistra-check-$(basename "$PWD")"
export COMPOSE_FILE COMPOSE_PROJECT_NAME

tree=
guard=
now() {
  TZ=Europe/Zagreb date '+%Y-%m-%d %H:%M'
}
timed() {
  phase=$1
  shift
  started=$(date +%s)
  outcome=0
  "$@" || outcome=$?
  took=$(($(date +%s) - started))
  spent="check: $phase took $((took / 60)):$(printf %02d $((took % 60)))"
  echo "$spent"
  [ "$mode" != push ] || echo "$(now) $tree $spent" >>"$store/push.log"
  return "$outcome"
}
finish() {
  status=$?
  [ -z "$guard" ] || kill "$guard" 2>/dev/null || true
  docker compose --profile check down --volumes --remove-orphans --timeout 5 >/dev/null 2>&1
  if [ "$mode" != push ] && [ -n "$tree" ] && [ "$status" != 0 ]; then
    echo "$tree failed $(now)" >>"$store/$mode"
  fi
  rm -rf "$run"
}
trap finish EXIT
trap 'exit 130' INT TERM

# The containers write here as users of their own.
chmod 777 "$run"
cp "$(git rev-parse --git-path index)" "$run/index"
GIT_INDEX_FILE="$run/index" git add -A
tree=$(GIT_INDEX_FILE="$run/index" git write-tree)

# The last tree each kind of test passed on: a full run's lines `tested` once all but the
# browser's passed, `passed` once the browser's did too.
since() {
  cat "$store/full" "$store/browser" 2>/dev/null | grep -E "^[0-9a-f]+ ($1) " | sort -s -k 3,4 | tail -n 1 | cut -d ' ' -f 1
}
case $mode in
push)
  for kind in full browser; do
    last=$(tail -n 1 "$store/$kind" 2>/dev/null || true)
    case $last in
    *" failed "*) echo "check: the last $kind run failed ($last): $store/$kind.log" >&2 ;;
    esac
  done
  if grep -q "^$tree " "$store/passed" 2>/dev/null; then
    echo "check: this tree has passed these checks already"
    exit 0
  fi
  # The base is the tree passed on nearest this one: the full run's or one a push's checks passed on.
  base=$(since 'passed|tested')
  nearest=$([ -z "$base" ] || git diff --name-only "$base" "$tree" | wc -l)
  for own in $(tail -n 30 "$store/passed" 2>/dev/null | cut -d ' ' -f 1); do
    git cat-file -e "$own" 2>/dev/null || continue
    apart=$(git diff --name-only "$own" "$tree" | wc -l)
    if [ -z "$base" ] || [ "$apart" -lt "$nearest" ]; then
      base=$own
      nearest=$apart
    fi
  done
  ;;
browser) base=$(since passed) ;;
full | shots) base= ;;
esac
if [ "$mode" != full ] && [ "$base" = "$tree" ]; then
  echo "check: nothing changed since the tree these tests passed on"
  [ "$mode" != push ] || echo "$tree $(now)" >>"$store/passed"
  exit 0
fi

# LXC 210 has no swap, and a gate beside other heavy work once took the whole container down
# (30.10.2026): the stack goes first.
(
  while sleep 5; do
    left=$(awk '/^MemAvailable:/ { print int($2 / 1024) }' /proc/meminfo)
    if [ "$left" -lt 3000 ]; then
      echo "check: $left MB of memory left; the stack is stopped" >&2
      docker compose --profile check kill >/dev/null 2>&1
      exit
    fi
  done
) &
guard=$!

selector() {
  docker compose run --rm --no-deps -T --entrypoint python -v "$PWD:/tree:ro" backend /tree/scripts/select.py "$1"
}

git ls-tree -r "$tree" -- e2e/tests >"$run/specs"
git ls-tree -r "$tree" -- backend >"$run/blobs"
[ ! -f "$store/corpus" ] || cp "$store/corpus" "$run/corpus.sealed"
everything=
if [ "$mode" = push ] || [ "$mode" = browser ]; then
  if [ ! -s "$store/map.json" ]; then
    everything="no full run has noted what its tests run"
  elif ! git cat-file -e "$base" 2>/dev/null; then
    everything="nothing has passed yet"
  else
    git diff --name-only --no-renames "$base" "$tree" >"$run/changed"
    git diff -U0 --no-renames --no-color --no-ext-diff --src-prefix=a/ --dst-prefix=b/ "$base" "$tree" >"$run/diff"
    for messages in hr en; do
      git show "$base:frontend/src/i18n/$messages.ts" >"$run/$messages.ts.base" 2>/dev/null || rm -f "$run/$messages.ts.base"
    done
    cp "$store/map.json" "$run/map.json"
    timed choice selector plan
    # shellcheck source=/dev/null
    . "$run/plan.env"
  fi
fi

stack() {
  # Made here, not by Docker, which would make the bind mount's folder root's.
  mkdir -p frontend/node_modules
  if ! docker compose up -d --wait --quiet-pull "$@"; then
    for down in $(docker compose ps -a --status exited --format '{{.Service}}'); do
      docker compose logs --no-color --tail=80 "$down" >&2
    done
    exit 1
  fi
}

# A test that fails and then passes is reported flaky (Playwright's summary, failed.json) and
# fails nothing. Playwright runs as many workers and tries as accounts are started, and leaves what
# it saw of a test that failed in $store/results.
browser() {
  # The browser's mail tests read mox@localhost whole, so what the backend's tests left there
  # in a full run would be theirs; restarting empties its tmpfs.
  docker compose restart mox >/dev/null || return
  session=$(docker compose exec -T backend python manage.py e2e_session start --workers=4 --retries=1) || return
  docker compose build -q e2e || return
  mkdir -p "$store/results"
  chmod 777 "$store/results"
  # A release building beside them fails the slower tests on time alone.
  flock "$store/release.lock" true
  rm -f "$store/$mode-servers.log"
  docker compose run --rm --no-deps -T -v "$store/results:/tmp/results" -e PONISTRA_SESSION="$session" \
    e2e node_modules/.bin/playwright test "$@" && return
  status=$?
  said
  return "$status"
}

# What the servers wrote during a browser run that failed, kept in $store/<mode>-servers.log in
# local time, as the stack and its logs go when the check ends.
said() {
  docker compose logs --no-color --timestamps backend frontend postgres reader 2>&1 |
    docker compose run --rm --no-deps -T --entrypoint python backend -c '
import re, sys
from datetime import datetime
from zoneinfo import ZoneInfo

zone = ZoneInfo("Europe/Zagreb")
stamp = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?Z ")
for line in sys.stdin:
    sys.stdout.write(stamp.sub(lambda found: datetime.fromisoformat(found[1] + "+00:00").astimezone(zone).strftime("%Y-%m-%d %H:%M:%S "), line, count=1))
' >"$store/$mode-servers.log"
  echo "check: what the servers wrote is in $store/$mode-servers.log" >&2
}

# The accounts help_seed fills, photographed in each language and scheme; what comes out replaces
# what the main checkout holds, which the dev frontend serves and a release takes.
shots() {
  session=$(docker compose exec -T backend python manage.py help_seed) || return
  docker compose build -q e2e || return
  mkdir -p "$run/shots"
  chmod 777 "$run/shots"
  taken=0
  docker compose run --rm --no-deps -T -v "$run/shots:/shots" -e PONISTRA_SHOTS="$session" \
    e2e node_modules/.bin/playwright test --config shots.config.ts "$@" || taken=$?
  for each in "$run/shots/"*.webp; do
    [ -e "$each" ] && cp "$each" "$(dirname "$(dirname "$store")")/help-shots/"
  done
  return "$taken"
}

failed=
stage() {
  name=$1
  shift
  "$@" || failed="$failed $name"
}

case $mode in
full)
  echo "check: everything"
  export PONISTRA_MAP=/map
  timed stack stack backend frontend printer livekit
  stage help timed help docker compose run --rm --no-deps -T --entrypoint python -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD:/tree:ro" backend /tree/scripts/help.py check
  stage ruff timed ruff docker compose exec -T backend sh -c 'ruff check . && ruff format --check .'
  stage pytest timed pytest docker compose exec -T backend pytest -q -n 3 --dist loadgroup --durations=25
  stage frontend timed frontend docker compose exec -T frontend sh -c 'npx prettier --check src && npm run typecheck'
  stage vitest timed vitest docker compose exec -T frontend npm test
  [ -n "$failed" ] || echo "$tree tested $(now)" >>"$store/full"
  stage browser timed browser browser
  stage shots timed shots shots
  [ ! -s "$store/map.json" ] || cp "$store/map.json" "$run/before.json"
  echo "$failed" >"$run/stages"
  echo "$tree" >"$run/tree"
  selector merge
  case " $failed " in
  *" pytest "*) ;;
  *) if mark=$(selector corpus); then echo "$mark all $(now)" >>"$store/corpus"; fi ;;
  esac
  mv "$run/map.json" "$store/map.json"
  mv "$run/failed.json" "$store/failed.json"
  if [ -n "$failed" ]; then
    echo "check: failed:$failed ($store/failed.json)" >&2
    exit 1
  fi
  ;;
browser)
  if [ -n "$everything" ]; then
    echo "check: every browser test, as $everything"
    E2E=all
  else
    echo "check: $(wc -l <"$run/changed") files changed since the browser's tests last passed; they reach $E2E"
  fi
  if [ "$E2E" != 0 ]; then
    timed stack stack backend frontend printer livekit
    if [ "$E2E" = all ]; then
      timed browser browser
    else
      # shellcheck disable=SC2046
      timed browser browser $(cat "$run/e2e.txt")
    fi
  fi
  ;;
push)
  if [ -n "$everything" ]; then
    echo "check: every test but the browser's, as $everything"
    BACKEND=1 FRONTEND=1 STACK=0 PYTEST=all VITEST=all CORPUS=all LANGUAGES=all FINGERPRINT=-
    select=
    : >"$run/vitest.txt"
  else
    [ "$FULL" = 0 ] || echo "check: the change reaches every test"
    corpus="the corpus $CORPUS"
    [ "$CORPUS" = 0 ] || corpus="$corpus in $LANGUAGES"
    [ "$FINGERPRINT" = - ] || [ "$CORPUS" != 0 ] || corpus="the corpus none, as it passed on this fingerprint"
    echo "check: $(wc -l <"$run/changed") files changed since the tree these tests passed on; they reach pytest $PYTEST, $corpus, vitest $VITEST"
    select=/map/pytest.txt
  fi
  timed help docker compose run --rm --no-deps -T --entrypoint python -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD:/tree:ro" backend /tree/scripts/help.py check
  if [ "$BACKEND" = 1 ]; then
    timed ruff docker compose run --rm --no-deps -T --entrypoint sh backend -c 'ruff check . && ruff format --check .'
  fi
  if [ "$FRONTEND" = 1 ]; then
    mkdir -p frontend/node_modules
    # shellcheck disable=SC2046
    timed frontend docker compose run --rm --no-deps -T --entrypoint sh frontend -c \
      'sh packages.sh && npx prettier --check src && npm run typecheck && if [ "$1" = all ]; then npm test; else shift; [ "$#" = 0 ] || npx vitest related --run --passWithNoTests "$@"; fi' \
      sh "$VITEST" $(cat "$run/vitest.txt")
  fi
  if [ "$PYTEST" != 0 ] || [ "$CORPUS" != 0 ] || [ "$STACK" = 1 ]; then
    # The stack a full run notes them in: they reach the meetings' server and the printer.
    timed stack stack backend frontend printer livekit
  fi
  if [ "$PYTEST" != 0 ] || [ "$CORPUS" != 0 ]; then
    ignore=--ignore=apps/engine/tests
    [ "$CORPUS" = 0 ] || ignore=
    languages=$LANGUAGES
    [ "$languages" != all ] || languages=
    # 5: none of the tests chosen is left, their files deleted.
    timed pytest docker compose exec -T -e PONISTRA_SELECT="$select" -e PONISTRA_LANGUAGES="$languages" \
      backend pytest -q -n 3 --dist loadgroup $ignore || [ "$?" = 5 ]
    [ "$CORPUS" = 0 ] || [ "$FINGERPRINT" = - ] || echo "$FINGERPRINT $ICU $LANGUAGES $(now)" >>"$store/corpus"
  fi
  echo "$tree $(now)" >>"$store/passed"
  exit 0
  ;;
shots)
  stack backend frontend
  shift
  shots "$@"
  ;;
esac
echo "$tree passed $(now)" >>"$store/$mode"
