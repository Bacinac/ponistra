#!/usr/bin/env sh
# scripts/help.py in the backend's image, the tree at /tree (check, seen, gaps, sync).
set -eu
cd "$(git rev-parse --show-toplevel)"
exec docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" --entrypoint python \
	-e PYTHONDONTWRITEBYTECODE=1 -v "$PWD:/tree" backend /tree/scripts/help.py "$@"
