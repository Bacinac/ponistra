#!/usr/bin/env sh
# Once per clone, before the first `docker compose up`: activate the tracked git
# hooks and write the first revision.json (absent, the backend's /api/version
# answers 503).
set -eu
cd "$(git rev-parse --show-toplevel)"

git config core.hooksPath scripts/git-hooks
./scripts/gen-revision.sh
echo "git hooks active (core.hooksPath=scripts/git-hooks)"
cat backend/revision.json
