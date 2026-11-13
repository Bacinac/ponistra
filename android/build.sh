#!/usr/bin/env bash
# Build the signed Ponistra app for Android inside the ponistra/android-builder container (D26).
#
#   ./build.sh                  lint, test, build, and put the APK on the shelf (dist/), which every
#                               installation serves at /android/ beside the web app
#   ./build.sh --check          signed release lint, test and build; the shelf is left alone
#   ./build.sh --debug          debug lint, test and build; no signing material needed
#   ./build.sh --init-keystore  one-time: generate the release signing keystore
#
# Runs only here; the keystore never leaves this box. Every phone and every installation's
# /.well-known/assetlinks.json knows the app by its key, so losing it strands them all.
set -euo pipefail
cd "$(dirname "$0")"

catalog() { sed -n "s/^$1 = \"\(.*\)\"$/\1/p" gradle/libs.versions.toml; }
PLATFORM="android-$(catalog compileSdk).$(catalog compileSdkMinor)"
BUILD_TOOLS="$(catalog buildTools)"
IMG="ponistra/android-builder:$( { cat builder.Dockerfile; echo "$PLATFORM $BUILD_TOOLS"; } | sha256sum | cut -c1-12)"
CACHE=ponistra-gradle-cache
RUN=(docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/project" -w /project
     -v "$CACHE:/gradle-cache" -e GRADLE_USER_HOME=/gradle-cache -e HOME=/gradle-cache/home "$IMG")

docker image inspect "$IMG" >/dev/null 2>&1 || docker build -t "$IMG" \
  --build-arg PLATFORM="$PLATFORM" --build-arg BUILD_TOOLS="$BUILD_TOOLS" - < builder.Dockerfile
docker volume inspect "$CACHE" >/dev/null 2>&1 || {
  docker volume create "$CACHE" >/dev/null
  docker run --rm -v "$CACHE:/gradle-cache" "$IMG" chown "$(id -u):$(id -g)" /gradle-cache
}

if [[ "${1:-}" == "--init-keystore" ]]; then
  umask 077
  mkdir -p keystore
  [[ -f keystore/ponistra.keystore ]] && { echo "keystore already exists — refusing to overwrite (losing it strands every phone)"; exit 1; }
  # PKCS12 keeps one password for the store and the key.
  PASSWORD=$(head -c 24 /dev/urandom | base64 | tr -d '/+=')
  "${RUN[@]}" keytool -genkeypair -v -keystore keystore/ponistra.keystore \
    -alias ponistra -keyalg RSA -keysize 4096 -validity 10950 \
    -storepass "$PASSWORD" -keypass "$PASSWORD" -dname "CN=Ponistra"
  chmod 600 keystore/ponistra.keystore
  cat > keystore/keystore.properties <<PROPS
storeFile=keystore/ponistra.keystore
storePassword=$PASSWORD
keyAlias=ponistra
keyPassword=$PASSWORD
PROPS
  echo "keystore generated."
  exit 0
fi

PUBLISH=true
DEBUG=false
case "${1:-}" in
  --check) PUBLISH=false ;;
  --debug) PUBLISH=false; DEBUG=true ;;
  "") ;;
  *) echo "usage: $0 [--check|--debug|--init-keystore]" >&2; exit 2 ;;
esac

# A release APK must keep its signing identity to install as an update. --debug exercises lint,
# tests and compilation without touching that identity.
if ! $DEBUG; then
  [[ -f keystore/keystore.properties ]] || { echo "no keystore — run ./build.sh --init-keystore first"; exit 1; }
fi

# The app's version is the position in history of the last commit that changed it, so an app
# nobody touched keeps its version and a phone is not offered the same app again.
SOURCES=(.)
COUNT=$(git rev-list --count "$(git log -1 --format=%H -- "${SOURCES[@]}")")
BASE=$(tr -d ' \t\r\n' < ../VERSION)
[[ "$BASE" =~ ^([0-9]+)\.([0-9]+)$ ]] || { echo "VERSION must be MAJOR.MINOR, got '$BASE'" >&2; exit 1; }
MAJOR=${BASH_REMATCH[1]} MINOR=${BASH_REMATCH[2]}
# Android orders updates by versionCode alone, so it carries the whole version rather than the
# commit count, which restarts whenever the history does.
(( MINOR < 100 && COUNT < 100000 )) || { echo "v${BASE}.${COUNT} does not fit the versionCode layout" >&2; exit 1; }
CODE=$(( MAJOR * 10000000 + MINOR * 100000 + COUNT ))
NAME="v${BASE}.${COUNT}"

if $PUBLISH; then
  [[ "$(git rev-parse --is-shallow-repository)" == "false" ]] \
    || { echo "shallow clone: commit counts are not versions here"; exit 1; }
  [[ -z "$(git status --porcelain -- "${SOURCES[@]}")" ]] \
    || { echo "uncommitted changes: a version names a commit, so commit first (or --check)"; exit 1; }
  SHELVED=$( [[ -f dist/ponistra.json ]] && sed -n 's/.*"versionCode": *\([0-9]*\).*/\1/p' dist/ponistra.json || echo 0)
  (( CODE >= SHELVED )) || { echo "the app would go down from $SHELVED to $CODE, which Android refuses"; exit 1; }
fi

if $DEBUG; then
  TASKS=(:app:lintDebug :app:testDebugUnitTest :app:assembleDebug)
else
  TASKS=(:app:lintRelease :app:testDebugUnitTest :app:assembleRelease)
fi
"${RUN[@]}" gradle --no-daemon -q --warning-mode=fail \
  -Papp.versionCode="$CODE" -Papp.versionName="$NAME" "${TASKS[@]}"

TESTS=$(sed -n 's/^<testsuite [^>]* tests="\([0-9]*\)".*/\1/p' app/build/test-results/testDebugUnitTest/TEST-*.xml | awk '{ n += $1 } END { print n }')
echo "OK tested: ${TESTS} unit tests passed"

if $DEBUG; then
  echo "OK debug build $NAME"
  exit 0
fi

APK=app/build/outputs/apk/release/app-release.apk
# Check the file Gradle just signed, not merely the keystore's configuration.
# conscrypt loads its native library; the JDK now asks that to be allowed, which the SDK's wrapper
# script does not pass.
REPORT=$("${RUN[@]}" java --enable-native-access=ALL-UNNAMED \
  -jar "/opt/android-sdk/build-tools/${BUILD_TOOLS}/lib/apksigner.jar" verify --verbose --print-certs "$APK")
grep -F 'Verified using v2 scheme (APK Signature Scheme v2): true' <<<"$REPORT" >/dev/null \
  || { echo "release signature v2 verification failed: $APK" >&2; exit 1; }
SIGNER=$(sed -n 's/^Signer #1 certificate SHA-256 digest: //p; s/^V2 Signer: certificate SHA-256 digest: //p' <<<"$REPORT" | sort -u)
[[ -n "$SIGNER" && "$SIGNER" != *$'\n'* ]] || { echo "release has no unique signing certificate: $APK" >&2; exit 1; }
PACKAGE=$("${RUN[@]}" "/opt/android-sdk/build-tools/${BUILD_TOOLS}/aapt2" dump packagename "$APK")
echo "OK signed: $APK $PACKAGE ($SIGNER)"

if ! $PUBLISH; then
  echo "OK checked: $NAME"
  exit 0
fi

mkdir -p dist
cp "$APK" dist/ponistra.apk
cat > dist/ponistra.json <<META
{
  "versionCode": ${CODE},
  "versionName": "${NAME}",
  "bytes": $(stat -c%s dist/ponistra.apk),
  "sha256": "$(sha256sum dist/ponistra.apk | cut -d' ' -f1)",
  "package": "${PACKAGE}",
  "sourceRevision": "$(git rev-parse HEAD)",
  "signerSha256": "${SIGNER}"
}
META
echo "OK dist/ponistra.apk $NAME ($(stat -c%s dist/ponistra.apk) bytes)"
