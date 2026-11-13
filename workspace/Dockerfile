# syntax=docker/dockerfile:1
# The owner's code workspace (D34): code-server, VS Code in the browser, on Debian with git, the
# SSH client, GitHub's CLI and Docker's, in PONISTRA's colours.
FROM docker:29.9.3-cli@sha256:2357639ad1ea7d0194134bf3292622fd4e562483966ed674e5d7c945b5f3b28d AS docker

FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS fetch
ARG CODE_SERVER=4.145.2
ARG GH=2.103.3
ARG COMPOSE=5.7.0
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
	&& rm -rf /var/lib/apt/lists/*
WORKDIR /fetch
RUN curl -fsSL "https://github.com/coder/code-server/releases/download/v$CODE_SERVER/code-server-$CODE_SERVER-linux-amd64.tar.gz" | tar -xz \
	&& mv "code-server-$CODE_SERVER-linux-amd64" code-server \
	&& curl -fsSL "https://github.com/cli/cli/releases/download/v$GH/gh_${GH}_linux_amd64.tar.gz" | tar -xz \
	&& mv "gh_${GH}_linux_amd64/bin/gh" gh \
	&& curl -fsSLo docker-compose "https://github.com/docker/compose/releases/download/v$COMPOSE/docker-compose-linux-x86_64" \
	&& chmod +x docker-compose
# Copilot and GitHub's API for it come under GitHub's own terms, terminal-suggest with fish's
# completions under the GPL.
RUN rm -r code-server/lib/vscode/extensions/copilot \
	code-server/lib/vscode/node_modules/@vscode/copilot-api \
	code-server/lib/vscode/extensions/terminal-suggest
# Any window that connects cuts the wait of every window away to five minutes, and a browser wakes a
# background tab only when it is looked at, so that tab's extension host and agents die. A window
# away waits the whole grace time start.sh gives it.
RUN cd code-server/lib/vscode/out \
	&& host=vs/workbench/api/node/extensionHostProcess.js \
	&& sed -i -E \
		-e 's/(let [a-zA-Z_$]+=)3e5(;this\._reconnectionShortGraceTime=)/\1Infinity\2/' \
		-e 's/(shortGraceTime:[a-zA-Z_$.]+>0\?Math\.min\()3e5,/\1Infinity,/' server-main.js \
	&& sed -i -E 's/(108e5\),[a-zA-Z_$]+=[a-zA-Z_$]+>0\?Math\.min\()3e5,/\1Infinity,/' "$host" \
	&& [ "$(grep -oE '=Infinity;this\._reconnectionShortGraceTime=|shortGraceTime:[a-zA-Z_$.]+>0\?Math\.min\(Infinity,' server-main.js | wc -l)" = 2 ] \
	&& [ "$(grep -oE '108e5\),[a-zA-Z_$]+=[a-zA-Z_$]+>0\?Math\.min\(Infinity,' "$host" | wc -l)" = 1 ]
COPY webview.mjs .
RUN code-server/lib/node webview.mjs code-server/lib/vscode/out/vs/workbench/contrib/webview/browser/pre/index.html
COPY theme.mjs .
COPY --from=theme theme.css .
RUN code-server/lib/node theme.mjs theme.css code-server/lib/vscode/extensions/ponistra-theme
# The first script of the page carries the nonce its Content-Security-Policy asks for.
COPY scheme.js .
RUN page=code-server/lib/vscode/out/vs/code/browser/workbench/workbench.html \
	&& [ "$(grep -c "performance.mark('code/didStartRenderer');" "$page")" = 1 ] \
	&& sed -i "\|performance.mark('code/didStartRenderer');|r scheme.js" "$page" \
	&& grep -q "ponistra.theme" "$page"
COPY phone.js .
COPY phone code-server/lib/vscode/extensions/ponistra-phone
RUN page=code-server/lib/vscode/out/vs/code/browser/workbench/workbench.html \
	&& [ "$(grep -c "performance.mark('code/willLoadWorkbenchMain');" "$page")" = 1 ] \
	&& sed -i "\|performance.mark('code/willLoadWorkbenchMain');|r phone.js" "$page" \
	&& grep -q "ponistra.phone" "$page"
COPY --from=brand favicon.svg favicon.ico icon-192.png icon-512.png icon-maskable-512.png mark.svg ./
RUN cd code-server/src/browser/media \
	&& cp /fetch/favicon.svg favicon.svg && cp /fetch/favicon.svg favicon-dark-support.svg \
	&& cp /fetch/favicon.ico favicon.ico \
	&& cp /fetch/icon-192.png pwa-icon-192.png && cp /fetch/icon-512.png pwa-icon-512.png \
	&& cp /fetch/icon-maskable-512.png pwa-icon-maskable-192.png \
	&& cp /fetch/icon-maskable-512.png pwa-icon-maskable-512.png
# The mark stands in for VS Code's icon on the title bar and for code-server's watermark in an empty
# editor, the watermark keeping the faintness its scheme gives it.
RUN cd code-server/lib/vscode/out \
	&& for icon in media/code-icon.svg vs/workbench/browser/media/code-icon.svg; do cp /fetch/mark.svg "$icon"; done \
	&& for press in media/letterpress-*.svg vs/workbench/browser/parts/editor/media/letterpress-*.svg; do \
		faint=$(grep -o '^<svg[^>]* opacity="[^"]*"' "$press" | grep -o 'opacity="[^"]*"'); \
		sed "1s/<svg /<svg $faint /" /fetch/mark.svg > "$press"; \
	done

FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
ENV LANG=C.UTF-8 HOME=/home/owner
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git openssh-client \
	&& rm -rf /var/lib/apt/lists/* \
	&& useradd --uid 1000 --create-home --shell /bin/bash owner \
	&& mv /etc/passwd /etc/passwd.base && ln -s /tmp/passwd /etc/passwd
COPY --from=fetch /fetch/code-server /usr/lib/code-server
COPY --from=fetch /fetch/gh /usr/local/bin/gh
COPY --from=docker /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/
COPY --from=fetch /fetch/docker-compose /usr/local/libexec/docker/cli-plugins/
COPY settings.json /etc/ponistra/settings.json
COPY projects.mjs chats.mjs memory.mjs terminal.mjs host.mjs /etc/ponistra/
# The terminal runs on code-server's own node-pty and ws; a code-server that moves either fails here.
RUN /usr/lib/code-server/lib/node --input-type=module -e "await import('/etc/ponistra/terminal.mjs')"
# Every chat says through its hooks when it has answered or waits on its owner (D52), for whatever
# settings of its own the owner keeps.
COPY heard.mjs /etc/ponistra/heard.mjs
COPY managed-settings.json /etc/claude-code/managed-settings.json
COPY start.sh /usr/local/bin/start
USER 1000:1000
WORKDIR /home/owner
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/start"]
