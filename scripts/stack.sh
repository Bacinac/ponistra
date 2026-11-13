#!/usr/bin/env sh
# A crash's stack as the server logged it (stdin), read through the maps of the frontend's release
# <version>: each frame of a built chunk becomes the line of our source it came from.
#   scripts/stack.sh 0.1.198 < crash.txt
set -eu
[ $# -eq 1 ] || {
	echo "usage: scripts/stack.sh <version> < stack" >&2
	exit 2
}
cd "$(git rev-parse --show-toplevel)"
STACK=$(cat)
export STACK
docker run --rm --entrypoint tar "ghcr.io/bacinac/ponistra-frontend:$1" -C /maps -cf - . |
	docker run --rm -i -e STACK -v "$PWD/scripts/stack.mjs:/stack.mjs:ro" node:26-alpine \
		sh -c 'mkdir /maps && tar -xf - -C /maps && node /stack.mjs /maps'
