# Installation

One installation is one organisation. It runs as a Docker Compose stack in a
directory of its own, which holds everything the installation is: `compose.yaml`,
`.env` with its secrets, the `ponistra` command and `volumes/` with the database,
the files and the snapshots.

## Requirements

- Linux with a current Docker Engine and the Compose v2 plugin.
- 4 cores and 6 GB of memory; imports, OCR and printing of large files are the
  peaks. The images take about 4 GB; documents, files and snapshots come on top.
- A domain that leads to the server, and port 443 (and 80) reachable from where
  people work, or a proxy or tunnel in front that ends TLS itself.

## Install

```bash
mkdir ponistra && cd ponistra
docker run --rm ghcr.io/bacinac/ponistra > ponistra && sh ponistra install
```

The release image prints its own `ponistra` command, which installs exactly
that release; `ghcr.io/bacinac/ponistra:<version>` pins one. `install` asks:

| Question | Answer | Ahead in the environment |
|---|---|---|
| Domain Ponistra is opened on | `office.example.com` | `PONISTRA_DOMAIN` |
| Where TLS ends | `here`: Caddy fetches and renews the certificate on port 443; `front`: a proxy or tunnel in front ends it and reaches Ponistra on port 80 | `PONISTRA_TLS` |
| Who gets the code workspace | an e-mail, or empty for none (below) | `PONISTRA_WORKSPACE` |
| Where the code workspace runs | `here`, or the `https://` address of one run elsewhere (below) | `PONISTRA_WORKSPACE_URL` |
| May its agent run Docker on this host | `no`, or `yes`, which is root on the host | `PONISTRA_WORKSPACE_DOCKER` |

It writes `.env` with every secret generated, prepares `volumes/`, starts the
stack and waits until the release answers. At the end it prints a one-time code
of sixteen characters, which stays in `.env` as `PONISTRA_SETUP_CODE`: open
`https://<domain>/`, enter the code and create the first administrator, who
then invites everyone else.

An unattended install answers every question ahead:

```bash
PONISTRA_DOMAIN=office.example.com PONISTRA_TLS=front PONISTRA_WORKSPACE=none sh ponistra install
```

`PONISTRA_HTTP_PORT` and `PONISTRA_HTTPS_PORT` in `.env` move the ports Caddy
listens on, for a server where something else holds 80 and 443.

## Meetings

Meetings carry sound and video over LiveKit, which runs on the host's own
network. Inside the local network nothing more is needed. From outside,
forward to the server:

| Port | For |
|---|---|
| UDP 7882 | media, the usual way |
| TCP 7881 | media where UDP is blocked |

Without these ports nothing from outside reaches the meeting: a relay
elsewhere does not stand in for them, as LiveKit has to be reached itself.
**Administration → Network** shows whether the public address answers on
them, and the health page warns the administrators when it stops.

For networks that let out neither, Ponistra runs a relay (TURN): point a name of
its own straight at the server (not through a proxy or tunnel), forward TCP 443
and UDP 3478 to the server and run `ponistra relay <that name>`. Caddy keeps
the relay's certificate as well. Where Cloudflare keeps that name and the
public address changes, a token of its zone (Zone: Read, DNS: Edit) entered
on **Administration → Network** keeps the record pointing at it.

## Mail, sign-in and AI

Everything else is set in the application, by an administrator, and kept in
the database: each user adds their own mail accounts, a mailbox at Google or
Microsoft signs in through the organisation's own OAuth client entered on
**Settings**, an outside
identity provider (OIDC or SAML) and a directory (LDAP or SCIM) are set up
there too, and the AI actions need the organisation's own Claude API key. Each
user agrees to the AI actions before the first one runs.

## The code workspace

One user of the installation, its owner, can have a code workspace: VS Code in
the browser and the **Projects** page, where Claude Code chats run in the
workspace and are followed and answered from Ponistra, the phone included.
`install` asks for it; `./ponistra workspace` adds it later. Without an answer
ahead it asks who gets it, where it runs and, when it runs here, whether its
agent may run Docker on the host.

### Here

The workspace is the stack's service `workspace` (`COMPOSE_PROFILES=workspace`
in `.env`), its home `volumes/workspace`, mounted inside at the same path as on
the host, so that whatever the agent mounts into a container of its own is found
there. It is reached only through Ponistra, at `/code/`, after the owner
confirms who they are, and every snapshot takes its home with it. It holds at
most 4 GB of memory.

On its first start the workspace installs the Claude Code extension from Open
VSX into its home: the image does not carry it, as it comes under Anthropic's
own terms. The owner then signs in once, with a Claude subscription or a
Console account:

1. Open **Projects** in Ponistra: on a computer in the rail, on a phone from the
   account menu.
2. Open the terminal of **General**.
3. Type `claude auth login`, open the address it prints, sign in and paste the
   code you are given back into the terminal.

The chats, the editor's Claude panel and the terminal share that sign-in. The
workspace reaches out to the internet: Open VSX for extensions, Anthropic for
the agent, and wherever its Git remotes are.

With Docker for the agent (`yes`), `COMPOSE_FILE` in `.env` lays
`compose.docker.yaml` over `compose.yaml`, which gives the workspace the host's
Docker socket. That is root on the host, and also what lets **Projects** restart
the workspace with its button, so without Docker the button is not shown.

### Elsewhere

The workspace can run on a machine of the owner's, for example one with more
memory or the owner's own files, from the release's image
`ghcr.io/bacinac/ponistra-workspace:<version>` behind a door of its own at an
`https://` address. The installation reaches its projects there with a token,
and the workspace tells the installation of every change with the same one.

1. Make a token, for example `openssl rand -hex 32`.
2. In Ponistra open **Administration**, **App sign-in** and add a **New
   application**: the redirect URI `https://code.example.com/oauth2/callback`,
   for **Administrators** if the owner is one. Keep its client ID and secret.
3. On the machine, in a directory of its own, put the owner's e-mail in a file
   `owner`, the token and the door's secrets in `.env` (`openssl rand -hex 16`
   for the cookie's), and this `compose.yaml`:

```yaml
services:
  door:
    image: quay.io/oauth2-proxy/oauth2-proxy:v7.15.6
    environment:
      OAUTH2_PROXY_PROVIDER: oidc
      OAUTH2_PROXY_OIDC_ISSUER_URL: https://office.example.com/api/identity
      OAUTH2_PROXY_CLIENT_ID: ${DOOR_CLIENT_ID:?set in .env}
      OAUTH2_PROXY_CLIENT_SECRET: ${DOOR_CLIENT_SECRET:?set in .env}
      OAUTH2_PROXY_COOKIE_SECRET: ${DOOR_COOKIE_SECRET:?set in .env}
      OAUTH2_PROXY_REDIRECT_URL: https://code.example.com/oauth2/callback
      OAUTH2_PROXY_UPSTREAMS: http://workspace:8080,http://workspace:8081/ponistra/
      # The installation's own requests, which the workspace checks against the token itself.
      OAUTH2_PROXY_SKIP_AUTH_ROUTES: ^/ponistra/(projects|commands|terminal|memory(/file|/write)?|files(/read|/raw|/write)?|hosts(/remove|/key)?|chats/[0-9a-f-]{36})$
      OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE: /owner
      OAUTH2_PROXY_HTTP_ADDRESS: 0.0.0.0:4180
      OAUTH2_PROXY_SKIP_PROVIDER_BUTTON: "true"
      OAUTH2_PROXY_CODE_CHALLENGE_METHOD: S256
      OAUTH2_PROXY_COOKIE_SECURE: "true"
      OAUTH2_PROXY_COOKIE_EXPIRE: 168h
      OAUTH2_PROXY_COOKIE_CSRF_PER_REQUEST: "true"
      OAUTH2_PROXY_SESSION_COOKIE_MINIMAL: "true"
    volumes:
      - ./owner:/owner:ro
    ports:
      - "4180:4180"
    restart: unless-stopped
  workspace:
    image: ghcr.io/bacinac/ponistra-workspace:<version>
    init: true
    user: "1000:1000"
    environment:
      HOME: /home/owner
      PONISTRA_PUBLIC_URL: https://office.example.com
      PONISTRA_WORKSPACE_TOKEN: ${PONISTRA_WORKSPACE_TOKEN:?set in .env}
    volumes:
      - ./home:/home/owner
    read_only: true
    tmpfs:
      - /tmp
    restart: unless-stopped
```

4. `mkdir home && sudo chown 1000:1000 home`, then `docker compose up -d`, and
   lead `https://code.example.com` to port 4180 through the proxy or tunnel that
   ends its TLS.
5. In the installation's directory, `./ponistra workspace` with the owner's
   e-mail, the address and the token.

The owner signs in to Claude Code as above. A workspace elsewhere has no
**Projects** restart button: it is restarted where it runs, and updated by
changing `<version>` to the installation's.

## Backup and restore

Every night the installation takes a snapshot of the database, the files, `.env`
and the code workspace into `volumes/backup`, encrypted with `RESTIC_PASSWORD`.
Between snapshots the database's log and the files are kept every fifteen
minutes, so the installation can go back to any moment of the last seven days.
Snapshots are kept daily for a week, weekly for a month and monthly for a year.

```bash
./ponistra backup                       # a snapshot now
./ponistra backups                      # the snapshots kept
./ponistra restore                      # as far forward as the log reaches
./ponistra restore "2026-11-13 09:30"   # a moment of the last seven days
./ponistra restore <snapshot>           # as one snapshot left it
```

Snapshots on the same disk do not survive the loss of the server. On
**System health**, set up the off-site copy to an S3-compatible bucket
(Cloudflare R2, Backblaze B2, AWS S3 and the like): it gives a recovery kit
once, which belongs away from the server. On a new server, in an empty
directory with the `ponistra` command of any release:

```bash
./ponistra recover <kit>
```

brings back the installation as the copy left it; then point the domain at the
new server.

## Update

```bash
./ponistra update              # the newest release
./ponistra update <version>    # a given one
```

An update takes a snapshot first, stops the old release and starts the new one.
If the new one does not start, the old release comes back with the database as
the snapshot left it, and the new one's log stays in `update-<version>.log`.
Each release updates to itself, so a jump over many releases is one command.
Going back to an older release is a restore, not an update.

## Everyday commands

```bash
./ponistra status              # each service and the version that answers
./ponistra access <email>      # a new password for someone locked out, printed once
docker compose logs -f backend
docker compose down            # stops the stack; the data stays
```

Never add `-v` to `docker compose down`, and never delete `volumes/`: that is
the installation.
