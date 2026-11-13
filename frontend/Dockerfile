FROM node:26-alpine@sha256:8996bb5821d62a8fd9bb27c1cb07462f3fdce6e47d640c6a881ead0b064ce216 AS node
RUN npm install -g npm@12.2.2 --no-audit --no-fund

FROM node AS deps
WORKDIR /app
COPY package.json package-lock.json packages.sh ./
COPY patches ./patches
RUN sh packages.sh

FROM node AS dev
ENV NODE_ENV=development
WORKDIR /app
COPY --from=deps --chown=node:node /app/node_modules ./node_modules
COPY --chown=node:node . ./
USER node
EXPOSE 5173
# V8 14.6, in every Node 26 release so far, aborts the process with "Lazy deopt after a fast
# API call with return value is unsupported" as Vite ends a response with a large module; the
# flag keeps TurboFan off that path until a Node release ships a V8 that no longer aborts.
CMD ["sh", "-c", "sh packages.sh && exec node --no-turbo-fast-api-calls node_modules/vite/bin/vite.js --host 0.0.0.0 --port 5173"]

FROM node AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=fonts . /fonts
COPY --from=colors . /colors
COPY --from=schema . /schema
COPY --from=android . /android
COPY --from=shots . /shots
COPY . ./
RUN npm run build && mkdir /maps && find dist -name '*.map' -exec mv {} /maps/ \;

FROM caddy:2-builder-alpine@sha256:a0fde94c08a09fc31a8f2aeb42d0c2003807a325f04efeb98fa6cc89e25682e0 AS layer4
# Meetings' relay shares 443 with the app through layer4 (S2-2), pinned as it still changes
# between versions. A commit past v0.1.2: v0.1.2 handed a connection's prefetched bytes to
# another one (#483), so a proxy keeping connections open got answers to its other requests.
RUN xcaddy build --with github.com/mholt/caddy-l4@eafc300ef23bcb2a28cc329a18e1e98bcd2b7cee

FROM caddy:2-alpine@sha256:78bd35025c7ba85961dd149ae670315129954e77abe2383ac47c89106b35ade9 AS caddy
COPY --from=layer4 /usr/bin/caddy /usr/bin/caddy
# The container opens ports 80 and 443 to its unprivileged user by sysctl and drops every
# capability, and the kernel refuses to start a binary that asks for one it cannot have.
RUN setcap -r /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile
EXPOSE 80 443 5173

FROM caddy AS prod
COPY --from=build /app/dist /srv
# Outside /srv: the repository is private, so the maps are read only from the image.
COPY --from=build /maps /maps
