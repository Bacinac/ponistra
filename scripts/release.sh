#!/bin/sh
# Releases origin's main, as it stands when the release starts, as MAJOR.MINOR.<commit count> (scripts/gen-revision.sh): the services' images,
# built at their prod targets from compose.override.yaml's definitions, and the release image
# (the compose files and the ponistra command, deploy/), pushed to ghcr.io/bacinac under that version,
# the release image also as latest; then the tag v<version>.
#
#   scripts/release.sh                build, push and tag
#   scripts/release.sh --file <dir>   also <dir>/ponistra-<version>.tar.gz, every image of the
#                                     release, for an installation that updates without the registry
#
# amd64 only until the printer has run on real arm64 hardware (S0, s0-2).
set -eu
cd "$(git rev-parse --show-toplevel)"

REGISTRY=ghcr.io/bacinac
SERVICES="frontend backend converter ocr printer recorder workspace"
SOURCE=https://github.com/Bacinac/ponistra

case "${1:-}" in
	"") out= ;;
	--file) out=$(realpath "${2:?usage: $0 [--file <dir>]}") ;;
	*) echo "usage: $0 [--file <dir>]" >&2; exit 2 ;;
esac

git fetch -q origin
# What a push brought through the gate, fixed here while other sessions commit on top of it.
commit=$(git rev-parse origin/main)

# The main checkout, wherever this runs from: the keystore lives only there.
main=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
# Held while building: the browser's tests the push started wait for it (scripts/check.sh).
mkdir -p "$main/.git/ponistra-check"
exec 7>"$main/.git/ponistra-check/release.lock"
flock 7
mkdir -p "$main/.worktrees"
tree=$(mktemp -d "$main/.worktrees/release.XXXXXX")
trap 'git worktree remove --force "$tree" 2>/dev/null || rm -rf "$tree"' EXIT
git worktree add -q --detach "$tree" "$commit"
scripts/gen-revision.sh --shipped "$tree/backend/revision.json" "$commit"
version=$(sed -n 's/^ *"version": "\(.*\)",$/\1/p' "$tree/backend/revision.json")
[ -n "$version" ] || { echo "release: no version in revision.json" >&2; exit 1; }
sed -i "s/@RELEASE@/$version/" "$tree/deploy/ponistra"
cp "$tree/compose.yaml" "$tree/compose.docker.yaml" "$tree/deploy/"
# The phone app is signed only here, where its keystore is, and rides in the frontend's image, which
# serves it to the installation's phones (D26).
cp -R "$main/android/keystore" "$tree/android/"
"$tree/android/build.sh"
# The help's pictures of the last night; a picture no night has made yet shows as its caption.
find "$main/help-shots" -maxdepth 1 -name '*.webp' -exec cp -t "$tree/help-shots" {} +

tags=
for service in $SERVICES; do
	tags="$tags --set $service.tags=$REGISTRY/ponistra-$service:$version"
done
# compose.yaml's settings and .env belong to an installation; building needs none of them, so each
# setting it requires stands in as a placeholder.
touch "$tree/.env"
placeholders=$(grep -o '[$]{[A-Z_]*:?' "$tree/compose.yaml" | sort -u | sed 's/^[$]{\(.*\):?$/\1=unused/')
# GHCR links a package to its repository by the source annotation on the image's index. The
# images pushed also stay in the local store, which --file saves from.
# shellcheck disable=SC2086
(cd "$tree" && env $placeholders PONISTRA_VERSION="$version" docker buildx bake --push \
	-f compose.yaml -f compose.override.yaml \
	--set '*.platform=linux/amd64' \
	--set "*.labels.org.opencontainers.image.source=$SOURCE" \
	--set "*.labels.org.opencontainers.image.version=$version" \
	--set "*.annotations=index,manifest:org.opencontainers.image.source=$SOURCE" \
	--set "*.annotations=index,manifest:org.opencontainers.image.version=$version" \
	--set backend.target=prod --set frontend.target=prod \
	$tags $SERVICES)
docker buildx build -q --push --platform linux/amd64 \
	--label "org.opencontainers.image.source=$SOURCE" --label "org.opencontainers.image.version=$version" \
	--annotation "index,manifest:org.opencontainers.image.source=$SOURCE" \
	--annotation "index,manifest:org.opencontainers.image.version=$version" \
	-t "$REGISTRY/ponistra:$version" -t "$REGISTRY/ponistra:latest" "$tree/deploy" >/dev/null

if [ -n "$out" ]; then
	images="$REGISTRY/ponistra:$version $(sed -n 's/^    image: \([^$]*\)$/\1/p' "$tree/compose.yaml" | tr '\n' ' ')"
	for service in $SERVICES; do
		images="$images $REGISTRY/ponistra-$service:$version"
	done
	# shellcheck disable=SC2086
	docker save $images | gzip > "$out/ponistra-$version.tar.gz"
fi

git tag "v$version" "$commit"
# The tag names a commit that reached origin through the gate already.
PONISTRA_SKIP_CHECK=1 git push -q origin "v$version"
echo "released $version"
