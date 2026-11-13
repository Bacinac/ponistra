#!/usr/bin/env sh
# Re-resolve the dependency locks from backend/requirements*.in, ocr/requirements.in and the
# package.json of the frontend, e2e and printer in throwaway containers; nothing installs on the host.
set -eu
cd "$(git rev-parse --show-toplevel)"

docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend:/w" -w /w ghcr.io/astral-sh/uv:0.13.5-python3.14-trixie-slim sh -c '
    uv pip compile -q --generate-hashes --python-version 3.14 --overrides overrides.txt requirements.in -o requirements.lock
    uv pip compile -q --generate-hashes --python-version 3.14 --overrides overrides.txt requirements-dev.in -o requirements-dev.lock'
# Debian trixie's python3, which the ocr image builds its venv from.
docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/ocr:/w" -w /w ghcr.io/astral-sh/uv:0.13.5-python3.14-trixie-slim sh -c '
    uv pip compile -q --generate-hashes --python-version 3.13 requirements.in -o requirements.lock'
# The frontend image's own npm, so that the locks are written by the npm that installs them.
node=$(docker build -q --target node frontend)
for package in frontend e2e printer; do
    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/$package:/w" -w /w "$node" \
        npm install --package-lock-only --ignore-scripts --no-audit --no-fund
done
# Every base image at the digest its tag names today, the index of all its architectures: a build
# is the same until the next lock, which takes what the tag has moved to.
git ls-files '*Dockerfile' 'compose*.yaml' 'compose*.yml' | while read -r file; do
    sed -nE 's/^(FROM[[:space:]]+|[[:space:]]+image:[[:space:]]+)([^[:space:]@$]+:[^[:space:]@$]+)(@sha256:[0-9a-f]{64})?([[:space:]].*)?$/\2/p' "$file" |
        grep -v '^ponistra/' | sort -u | while read -r image; do
        digest=$(docker buildx imagetools inspect "$image" --format '{{.Manifest.Digest}}')
        pattern=$(printf '%s' "$image" | sed 's/[.]/\\./g')
        sed -i -E "s#^(FROM[[:space:]]+|[[:space:]]+image:[[:space:]]+)$pattern(@sha256:[0-9a-f]{64})?([[:space:]]|\$)#\1$image@$digest\3#" "$file"
    done
done
