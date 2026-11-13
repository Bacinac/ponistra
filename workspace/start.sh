#!/bin/sh
set -eu
: "${PONISTRA_PUBLIC_URL:?not set: where the installation is reached from outside}"
: "${PONISTRA_WORKSPACE_TOKEN:?not set: what the installation asks for the projects with}"
# ssh and ssh-keygen take the home from the user's entry, not from HOME, which compose sets to
# the same path as on the host.
sed "s|^owner:.*|owner:x:$(id -u):$(id -g):Owner:$HOME:/bin/bash|" /etc/passwd.base > /tmp/passwd
# The owner's settings start from PONISTRA's; once written they are the owner's to change.
settings="$HOME/.local/share/code-server/User/settings.json"
if [ ! -e "$settings" ]; then
	mkdir -p "${settings%/*}"
	cp /etc/ponistra/settings.json "$settings"
fi
# The agent finds PONISTRA's own MCP server (D18) listed from the start; signing in to it stays
# the owner's, and so does the file once written.
agent="$HOME/.claude.json"
[ -e "$agent" ] || (umask 077 && printf '{"mcpServers": {"ponistra": {"type": "http", "url": "%s/api/mcp"}}}\n' \
	"${PONISTRA_PUBLIC_URL%/}" > "$agent")
[ $# -gt 0 ] || set -- "$HOME"
for root; do :; done
export PONISTRA_ROOT="$root"
/usr/lib/code-server/lib/node /etc/ponistra/projects.mjs &
# A shell opened here would pass these to `docker compose`, where they outrank a project's own .env.
unset PONISTRA_PUBLIC_URL PONISTRA_WORKSPACE_TOKEN
# Three days cover a laptop asleep over a weekend. A window lost for good holds its processes this
# long against the container's memory limit, so not longer.
exec /usr/lib/code-server/bin/code-server \
	--bind-addr 0.0.0.0:8080 --auth none --reconnection-grace-time 259200 \
	--disable-telemetry --disable-update-check --disable-getting-started-override \
	--app-name Ponistra "$@"
