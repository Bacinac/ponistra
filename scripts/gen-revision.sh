#!/usr/bin/env sh
# Write the app revision as JSON, git being its only source: MAJOR.MINOR from
# ./VERSION (bumped by hand per milestone), patch = commit count, plus the exact
# commit. The file is never committed; the backend reads it per request.
#
#   scripts/gen-revision.sh                    backend/revision.json, dirty from the working tree
#   scripts/gen-revision.sh --shipped <file> <commit>   the commit exactly as a release ships it
set -eu

cd "$(git rev-parse --show-toplevel)"

OUT=backend/revision.json
REV=HEAD
if [ "${1:-}" = "--shipped" ]; then
    OUT=${2:?usage: $0 --shipped <file> <commit>}
    REV=${3:?usage: $0 --shipped <file> <commit>}
    DIRTY=false
elif git diff --quiet --ignore-submodules HEAD 2>/dev/null; then
    DIRTY=false
else
    DIRTY=true
fi

if [ "$REV" = HEAD ]; then
    BASE="$(tr -d ' \t\n\r' < VERSION)"
else
    BASE="$(git show "$REV:VERSION" | tr -d ' \t\n\r')"
fi
COUNT="$(git rev-list --count "$REV" 2>/dev/null || echo 0)"
SHA="$(git rev-parse --short=8 "$REV" 2>/dev/null || echo unknown)"
COMMITTED_AT="$(git log -1 --format=%cI "$REV" 2>/dev/null || echo unknown)"

cat > "$OUT" <<EOF
{
  "version": "${BASE}.${COUNT}",
  "base": "${BASE}",
  "count": ${COUNT},
  "sha": "${SHA}",
  "committed_at": "${COMMITTED_AT}",
  "dirty": ${DIRTY}
}
EOF
