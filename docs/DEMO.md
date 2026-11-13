# Ponistra demo

The public demo at [demo-ponistra.boskovic.biz](https://demo-ponistra.boskovic.biz)
(Cloudflare Pages project `ponistra-demo`) is the production React application
with a synthetic API loaded before the application starts. No request can
reach a Ponistra backend. It signs in as the fictional administrator `demo` and
never asks for a real credential; it speaks English until the visitor picks
another language.

## What is inside

A made-up company with a dozen people in their groups, at a domain reserved for
examples: documents with headings, tables, pictures and comments, tables with
formulas and charts, presentations, PDF files, folders of files and their
versions, mail in threads with attachments and flags, a calendar with
invitations and rooms, contacts, tasks, chat with reactions, a past meeting with
its minutes, boards, links, notes and favourites. The company, its people and
everything they wrote are fictional.

Editing works: a document opens with its recorded state and takes changes in
the tab, the way several people would. What is written (a new document, a sent
message, a task, a chat message) lives only in the current tab and disappears
on reload. What only a server can do (the AI actions, importing and exporting
files, printing, OCR, meetings) says plainly that it does not work in the demo.

## Credits

The pictures in the demo are CC0 or CC-licensed works from Wikimedia Commons, or
were generated for it and show no real person. Every file's author, licence,
source and the change made to it is listed in the seed's `credits` and shown at
`/demo-credits.html`, linked from the demo's banner.

## How it is made

One seed makes the company for both the demo and the help's screenshots:
`manage.py help_seed` (`backend/apps/help/seeds/`). `scripts/demo.sh` then:

1. starts a stack of its own from the development images (`compose.check.yml`),
   seeds it, and walks every page in Chromium as the seed's English
   administrator, recording each answer
   of the API into `frontend/demo/recorded/` (`responses.json`, binary bodies
   under `blobs/<sha256>`, each tab's Yjs state under `collab/<tab id>.bin`);
2. builds the application in the `demo` mode, in which `frontend/demo/` answers
   `/api` from that recording and serves live changes and co-editing locally;
   nothing in `frontend/demo/` is part of a production build;
3. walks the built demo without a network and makes and writes a new document,
   where any request that reaches `/api`, an answer the recording lacks or a
   blank page fails the build and names the page it came from;
4. passes every built file through the clone's `publicgate.command`, the same
   gate that guards the repository; a clone without one does not build the demo.

```bash
scripts/demo.sh             # record, build, walk and gate into .git/ponistra-check/demo
scripts/demo.sh --shots     # also retake docs/screenshots
scripts/demo.sh --deploy    # also publish to the Pages project
```

Publishing takes the Cloudflare token every boskovic.biz site deploys with,
`/mnt/docker/web/.cf-token` (`PONISTRA_CF_TOKEN_FILE` names another). For a
local look at a built demo, with its routes falling back to the app:

```bash
docker run --rm -p 8088:3000 -v "$PWD/.git/ponistra-check/demo:/site:ro" node:26-alpine npx -y serve -s /site
```
