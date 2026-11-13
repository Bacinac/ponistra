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

For networks that let out neither, Ponistra runs a relay (TURN): point a name of
its own straight at the server (not through a proxy or tunnel), set
`PONISTRA_TURN=<that name>` in `.env`, forward TCP 443 and UDP 3478 to the
server and run `docker compose up -d`. Caddy keeps the relay's certificate as
well. Where Cloudflare keeps that name and the public address changes,
`PONISTRA_CLOUDFLARE_TOKEN` (Zone: Read, DNS: Edit) keeps the record pointing
at it.

## Mail, sign-in and AI

Everything else is set in the application, by an administrator, and kept in
the database: each user adds their own mail accounts, a mailbox at Google or
Microsoft signs in through the organisation's own OAuth client entered on
**Settings**, an outside
identity provider (OIDC or SAML) and a directory (LDAP or SCIM) are set up
there too, and the AI actions need the organisation's own Claude API key. Each
user agrees to the AI actions before the first one runs.

## The code workspace

The installation's owner can have VS Code in the browser, behind Ponistra's
sign-in, with the agent they install and sign in to themselves. `install` asks
for it; `./ponistra workspace` adds it later. It runs in the installation, or
elsewhere at an `https://` address of the owner's. Letting its agent run Docker
on the host is asked separately and is root on that host.

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
