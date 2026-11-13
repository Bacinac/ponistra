#!/bin/sh
# node_modules from the lock and the patches, unless they are what is installed already. On LXC 210
# node_modules is the tree's own folder, which the editor on the host reads too, so the dev
# container installs into it as it starts; the dev stack and a check stack share that folder,
# hence the lock around the install.
set -eu
lock=$(cat package-lock.json patches/* | sha256sum)
mkdir -p node_modules
exec 9<node_modules
flock 9
if [ "$(cat node_modules/.installed 2>/dev/null)" != "$lock" ]; then
    npm ci --no-audit --no-fund
    echo "$lock" >node_modules/.installed
fi
