#!/usr/bin/env sh
# The gate's runs that a push does not wait for, over a commit in a worktree of their own
# (.worktrees/full), so that no tree in use is read:
#
#   scripts/check-full.sh [commit]            every test (scripts/check.sh --full), over main unless
#                                             a commit is named: each night from cron
#   scripts/check-full.sh --browser <commit>  the browser's tests the change reaches, started by
#                                             the pre-push hook for the commit pushed to main
#
# Runs wait for each other. Of the browser's runs one waits at most, and it takes the newest commit
# pushed once its turn comes. Each kind's output is kept in .git/ponistra-check/<kind>.log.
set -eu
cd "$(git rev-parse --show-toplevel)"

kind=full
if [ "${1:-}" = --browser ]; then
  kind=browser
  shift
fi
common=$(git rev-parse --path-format=absolute --git-common-dir)
store=$common/ponistra-check
full=${common%/.git}/.worktrees/full
mkdir -p "$store"

if [ "$kind" = browser ]; then
  git rev-parse --verify "$1^{commit}" >"$store/pushed"
  exec 8>"$store/browser.queue"
  flock -n 8 || exit 0
fi
exec 9>"$store/full.lock"
flock 9
if [ "$kind" = browser ]; then
  exec 8>&-
  commit=$(cat "$store/pushed")
else
  commit=$(git rev-parse --verify "${1:-main}^{commit}")
  if grep -q "^$(git rev-parse "$commit^{tree}") passed " "$store/full" 2>/dev/null; then
    echo "check-full: $(git rev-parse --short "$commit") has passed in full already"
    exit 0
  fi
fi

status=$(mktemp)
trap 'rm -f "$status"' EXIT
(
  trap 'echo "$?" >"$status"' EXIT
  echo "check-full: $kind, $(git log -1 --format='%h %s' "$commit" | cut -c 1-100), $(TZ=Europe/Zagreb date '+%Y-%m-%d %H:%M')"
  [ -d "$full" ] || git worktree add -q --detach "$full" "$commit"
  cd "$full"
  git checkout -q --force --detach "$commit"
  git clean -q -fd
  ln -sfn ../../.env .env
  scripts/gen-revision.sh
  scripts/check.sh "--$kind"
) 2>&1 | tee "$store/$kind.log"
exit "$(cat "$status")"
