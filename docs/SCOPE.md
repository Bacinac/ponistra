# PONISTRA — Scope

One application for everyday office work (text, spreadsheets, presentations,
PDF) running on our own hardware, with every document's content in Postgres.
Decided 2026-10-16.

## In scope

- One kind of document (D8): text with headings, lists, images and computing
  tables, in tabs. Word, Excel, PDF and slides are its outputs, not other kinds
  of document: the whole document saves as docx and prints to PDF, a table
  saves as xlsx, and the headings make the slides.
- Uploaded PDFs are files in the tree beside folders and documents: viewed,
  searched (OCR for scans) and embedded in documents.
- Native document model (D8): content stored as Yjs CRDT state in Postgres, one
  room per tab, with an element table derived from it for search, AI and SQL.
- Real-time co-editing by several people and devices from day one.
- One upload for every file. Office files become documents, with no fidelity
  guarantee for complex layouts: docx, odt, doc and rtf as text, xlsx, ods and xls as a
  tab with a table per sheet, pptx, odp and ppt as slides of the text (D13 *Slides*). Word,
  Excel and PowerPoint files with macros and templates (docm, dotx, dotm, xlsm, xltx, xltm,
  pptm, potx, potm, ppsx, ppsm) come in as docx, xlsx and pptx, their
  macros reported as left out, with their source to read. The original file stays with the
  document and can always be downloaded under its own extension. PONISTRA's own file
  (`.ponx`, D10) comes back as the document it was. PDFs stay files.
- One search across everything: document text, table cells, PDF files, OCR'd scans.
- Actions (D14): what Office does with dialogs and wizards comes as named actions in
  the command registry, carried out by our own code wherever a rule can be written and
  by an AI model only where the task needs language, and only after the user agrees.
- Outside agents (D18): PONISTRA is an MCP server, so an agent a user lets in reads
  and changes documents in that user's name, through the same actions and operations
  as the editor.
- Boards (D36): pages of HTML an agent writes or a user brings, shown as they are in a
  sandbox that keeps them from PONISTRA, with every page written over kept as a version,
  on a page of their own by the project or subject each belongs to (D47).
- A code workspace for the installation's owner (D34): VS Code in the browser, with
  the agent the owner installs and signs in to themselves; chosen at install, run
  in the installation or at an address of the owner's elsewhere.
- The rest of a firm's day without Microsoft 365 (D15): a mail client over the
  mailboxes people already have, calendar and contacts, chat and meetings, on the
  same directory, Postgres, search and actions. Each organisation installs it on
  its own hardware.
- Free and whole on its own; joined to TaskStreamer only when an administrator
  connects it, and then stronger for it (D17).
- Our production is an installation on mlaka (D1), developed on LXC 210, which serves the
  dev installation under a name of its own (D7).

## Out of scope

- Faithful round-tripping of complex Office files exchanged with outside parties.
- Desktop apps (D32: the app installed from the browser serves a computer), and native
  mobile apps beyond the Android app of D26 (the web app is responsive; an iPhone installs
  it and reads contacts and calendar over CardDAV and CalDAV).
- Cloud hosting and multi-tenancy: one installation is one organisation (D15).
- A mail server of our own: mail is a client of existing mailboxes (D15).
  Telephony, device management, the desktop OS and BI.
- Running VBA macros. The import report shows their source read-only, read from the VBA
  project by our own MS-OVBA reader over olefile (oletools is out: it needs the GPL pcodedmp);
  what a macro is for comes as a command of our own, as Excel's paste values does as
  "Duplicate as values". The xlsm, docm and pptm export (F4) gives the original VBA project back.

## Options

Not planned, possibly never needed; each is taken up when its trigger occurs and only then
enters the plan as a step.

- **arm64 builds of every engine** (former S0-2). Proven under QEMU on the dev host
  (2026-10-23): all five production images build for arm64 in 12 min, the stack starts,
  migrates and answers; the Tracking import (peak 648 MB), the converter and OCR work.
  IronCalc cross-compiles for aarch64 on amd64 in 5 min 26 s. Missing: the printer
  (Chromium under qemu-user cannot start its subprocesses) and real arm64 timings.
  Trigger: an installation on arm64, Ivo's Raspberry Pi 4 the first.
- **The connection with TaskStreamer** (former S6, D17): the connection (OAuth, outward
  only), notes and mail handed over, its tasks and Beats in the calendar and Today, its
  clients and suppliers as an address book, its documents made in Ponistra and its search
  over chosen folders, with TaskStreamer's side of the API; 2–3 weeks in both. Taken out of
  the plan 2026-11-13 (Ivo: "slažem se"): TaskStreamer already has its own mail, shared
  mailboxes per client, calendar, messaging, documentation search and offers, so the bridge
  mostly joins what both sides hold; under PolyForm NC a company on TaskStreamer uses
  Ponistra only with a licence of its own, so no one uses both; and an OAuth provider and a
  public API in a multi-tenant production SaaS stay to be kept for good. TaskStreamer keeps
  the path open (no change that would close it). Trigger: the first company holding a
  licence for Ponistra and a tenant in TaskStreamer asks for it, a Ponistra installation
  for the first customer installation the likeliest.

## Licence rule (hard)

Allowed: MIT, Apache-2.0, BSD and 0BSD, ISC, MPL-2.0, PostgreSQL, BlueOak-1.0.0,
Python-2.0, CC0-1.0 and the Unlicense (no rights reserved; CC0 grants no patent,
which a binding that only calls a library does not need: libarchive-c, D23), and
LGPL for unmodified
libraries used as they are (psycopg and its pool are LGPL-3.0, and Django has
no other Postgres driver). Fonts may also be SIL OFL-1.1, which allows
bundling and embedding them in documents and PDFs (D9); the exception covers
fonts only. Icons and images may be CC-BY, which asks for their authors' names in
NOTICE (VS Code's codicons and Git's logo, D34). GPL programs only as an image's
base system (Debian's shell and core utilities) and as git in the code workspace
(D34): unmodified, run as commands of their own, linked into nothing of PONISTRA's,
their source in Debian's archive. Excluded: GPL, AGPL, SSPL, BSL and every commercial or "Pro"
tier. Already ruled out by it: OnlyOffice, MuPDF, HyperFormula, Tiptap Pro,
Univer Pro, MinIO, the Redis server, Stalwart, Matrix Synapse
and Element, Mattermost, Zitadel, ClamAV. Others install PONISTRA themselves
(D15), so every dependency's notices ship with it.

PONISTRA itself is under the PolyForm Noncommercial License 1.0.0 (D29), whose
terms no GPL or AGPL input would allow: permissive inputs leave Ivo, as sole
holder, free to license PONISTRA as he chooses, a firm's commercial licence
included.

## Architecture

| Layer | Choice | Licence |
|---|---|---|
| Backend | Django 6.1, ASGI under uvicorn | BSD |
| Database | Postgres 18 | PostgreSQL |
| Frontend | React 19, Vite 8, Tailwind 4, TanStack Query, React Router, Radix UI, Lucide icons, TypeScript 7; a Radix menu stays modal, so the release of a long press does not click the row beneath it, but no longer hides the page behind it with `aria-hidden`, which WCAG refuses while the page holds what takes focus (`frontend/patches/` drops its `hideOthers`) | MIT, ISC (Lucide) |
| Collaboration | Yjs + y-websocket in the browser; pycrdt-websocket rooms inside the backend's ASGI app, updates in Postgres (D2). A room is one tab, and each document has one more for what its tabs share (theme and styles); trashing the document or deleting the tab closes its open sessions | MIT |
| Login | Django sessions, email as the user name, passkeys through py_webauthn; django-axes locks an account on one address after 5 failures for 15 minutes, an address after 30 across every account, and an account after 30 from everywhere, though only for addresses it never signed in from, so nobody outside can lock its owner out (`apps/users/throttle.py`) | BSD, MIT |
| Document tree | folders, documents and files in Postgres, a document holding its tabs (D8); trash with restore, permanent deletion only from the trash; names in Croatian collation (ICU). Postgres keeps every reference: deleting a row takes what belongs to it and clears who made it, and a blob still used cannot go, whatever path deletes, so a writer racing a deletion leaves no orphan | — |
| File bytes | content-addressed tree (SHA-256) under `volumes/blobs`, one upload for every kind of file (`/api/uploads`, in pieces of 32 MB under Cloudflare's 100 MB a request, each sent again from where the backend got to; at most `PONISTRA_FILE_MAX_GB`, 10 by default, refused while the disk lacks room, D23), served with byte ranges; metadata, versions and permissions in Postgres, every user of the bytes a foreign key. Bytes nothing refers to go in the background once something is purged, and in an hourly sweep, uploads younger than an hour spared: the collector walks every file kept, which no purge waits for. A PDF file in the tree holds one, which pdf.js reads by those ranges | — |
| Background work | loops in the ASGI lifespan over Postgres (LISTEN/NOTIFY, a sweep, `SKIP LOCKED`): versions, page counts, PDF text, OCR, the documents an action over a folder goes through, the jobs a user hands over that take longer than a request is given (saving as a file, importing, copying, composing pages). No worker process of its own: the rooms a job writes into live in the backend's event loop, and uvicorn runs one process (2026-10-22, Celery and Valkey dropped) | PostgreSQL |
| Document editor | ProseMirror with y-prosemirror (D3): a tab's text under `body`, each table's row and column ids, formulas, number formats and computed values under `tables` by the table block's id; `apps/content` reads and writes both | MIT |
| Computing tables | a block of the document, our own grid; our own engine computes the formulas on the server, in SQL over Postgres and in Python (`apps/engine`, D22); PyICU over the system ICU sorts text in the document's language; numpy, built without BLAS, adds up the sums of D22's sweep; D22's engine compares text by the Windows Sorting Weight Table Microsoft publishes with [MS-UCODEREF] | MIT, Unicode, BSD-3, Microsoft Open Specifications |
| Slides | the document shown slide by slide, laid out by the document's slide template (D13 *Slides*); pptx both ways through python-docx's OPC layer | MIT |
| PDF files | pdf.js (render, annotate), qpdf / pikepdf (structure, write), Tesseract through ocrmypdf (OCR, in the `ocr` service) | Apache-2.0, MPL-2.0, LGPL-3.0 (ocrmypdf's fpdf2 and img2pdf, unmodified) |
| Office import/export | python-docx and lxml for docx both ways (D13), our own reader and writer over zipfile and lxml for xlsx both ways, as streams (D22), and the workbook a docx or pptx chart embeds, python-docx's OPC layer and lxml for pptx both ways; Pillow sizes a Word file's images and turns WebP and AVIF, which Word does not read everywhere, into PNG; LibreOffice headless turns odt, doc and rtf into docx, ods and xls into xlsx, and odp and ppt into pptx | MIT, BSD, BSD-2-Clause, MIT-CMU, MPL-2.0 |
| Printing to PDF | Chromium headless through playwright-core, in the `printer` service: it saves the document's print page as PDF in the reader's own session | BSD, Apache-2.0 |
| Charts | ECharts with its SVG renderer, loaded once a chart appears; the server computes what a chart shows | Apache-2.0 |
| Actions | one layer of operations on the document model in `apps/content`, used by actions, the importer and the model's tools; actions defined in the backend and shown through the command registry (D14); the document schema in `schema/schema.json`, read by the editor and by the backend through prosemirror-py, attribute values checked with jsonschema | BSD-3-Clause, MIT |
| AI | the Claude API through its Python SDK, only for actions that need language and only after the user agrees (D14); the installation's key encrypted through cryptography; lingua knows a text's language on the server, with nothing sent (D35) | MIT; Apache-2.0 OR BSD-3-Clause; Apache-2.0 |
| Outside agents | the MCP Python SDK's server at `/api/mcp` inside the backend's ASGI app, and its authorization-server handlers over a store in Postgres (`apps/agents`) for the OAuth sign-in with a consent page (D18); tokens and client secrets kept as digests | MIT |
| Code workspace | code-server, VS Code in the browser, in the `workspace` service for the installation's owner alone, behind PONISTRA's sign-in, or elsewhere behind a door of the owner's; extensions from Open VSX, the agent's installed by the owner (D34) | MIT |
| Mail | a client over the account's own mailbox (D15): IMAPClient for IMAP, the standard library's smtplib for SMTP, nh3 for the text of an HTML part; mox as the mail server of the dev and check stacks; S/MIME and OpenPGP opened, signed and encrypted in the browser alone with keys from the vault (U5), through PKI.js and asn1js and OpenPGP.js (loaded once a sealed message is met), trust by the first key seen for an address | BSD-3-Clause, MIT, LGPL-3.0 (OpenPGP.js, unmodified) |
| Contacts | one address book per user from every account (D15, S4): ActiveSync's Contacts folder and directory, Microsoft Graph's contacts, Google's CardDAV; vCard read and written by our own `apps/contacts/vcard.py`, phone numbers through phonenumbers; CardDAV for a phone's own app (RFC 6352, sync-collection RFC 6578) served by our own `apps/dav`, which CalDAV joins in S4-2, signed in with app passwords | Apache-2.0 |
| Calendar | one calendar module per user over every account (D15, S4-2): Traveler's Calendar folder over ActiveSync read-only, Microsoft Graph's calendars and Google's older CalDAV endpoint taken once; iCalendar read and written through `icalendar`, recurrences expanded by the backend through `python-dateutil`'s rruleset; CalDAV for a phone's own app (RFC 4791, sync-collection RFC 6578) served by the same `apps/dav`, the same app passwords | BSD-3-Clause; Apache-2.0 OR BSD-3-Clause |
| Meetings | LiveKit server in the installation (D15, S2), on the host's network: signalling and its API on 7880 behind the app's `/livekit`, media on one UDP port (7882) and one TCP port (7881); livekit-client draws our own interface in the browser; a meeting is a row in Postgres and the backend signs each joining through PyJWT; our own `recorder` service (Go: LiveKit's server SDK, pion, ebml-go) writes each participant's tracks as WebM without transcoding (S2-5) | Apache-2.0, MIT, BSD |
| Fonts | seventeen families in `fonts/`, regular, bold and italic each, served by us (D9): Inter, Source Serif 4, IBM Plex Sans, Serif and Mono, Noto Sans and Serif, Intos, Intos Display, Narrow and Serif, Liberation Sans, Serif and Mono, Carlito, Caladea, Gelasio; `fonts/fonts.json` lists them with the Office fonts each stands for | OFL-1.1 |

File bytes stay outside Postgres: large binary values bloat WAL and backups and
cannot be range-streamed to pdf.js. On one node a content-addressed tree on ZFS
is the single store for bytes; everything about a file lives in Postgres.

A PDF file opens in pdf.js's own viewer components (F5), not the browser's: pages
are drawn only as they come into view, and the file is fetched by byte ranges for
those pages alone, so a long file opens as fast as a short one. Its character
maps, standard fonts, image decoders and colour profiles are served from the
pdf.js package under its version. The view shares the Pages view's zoom; the
file's bookmarks stand in the side column as a document's headings do
(`?heading=`), `?page=` opens a page and a search hit adds `?find=` to mark the
word it found; Ctrl+F finds across every page. A file locked by a password asks
for it in the browser, and the password never reaches the server.

An image uploaded among the documents (PNG, JPEG, GIF, WebP, AVIF, SVG) stays the
file it is, as a PDF does (2026-10-27): it shows as itself, sandboxed as the
editor's images are, to share, download or open on its own, and goes into a
document from its folder through the editor's Image dialog, beside one from the
computer. What only a PDF has (pages, notes, comments, text read, joining, the
actions over files) is not offered for it. Every other file is kept too, whatever
its kind (2026-10-27): it is shared and moved as any file is. A text file shows
as its text and a recording plays in the browser's player (D23); anything else
is only downloaded, never shown in the browser. A file's name is kept as Windows shows it,
the title apart from the extension it came with (2026-10-27). The bytes decide what
PONISTRA does with a file (shows it as a PDF or an image, imports it, saves it only);
the extension names its kind (the Kind column says "MP4 file", the icon, the name it
downloads under, the type an unknown file is sent as), so an Illustrator file opens
in the PDF viewer as the PDF it is and still reads "AI file" and downloads as `.ai`.
A file without one takes the extension of its bytes' kind. An Office
file the import cannot read (unreadable, too many cells or different formulas, too large, from a newer
PONISTRA) is kept as such a file and the upload says why; an Office file kept so
is searched by its text. A folder uploads whole, picked or dropped: the folders
below it are made where its files need them, a file or folder below it whose name
starts with a dot stays out, and what fails is listed after. Uploads belong to the
app, not to the page, so their progress follows the user from folder to folder.

Dragging, with a mouse: rows of a folder (one, or those chosen) go onto a folder
row, a folder of the side tree, a step of the path above or Trash; files and
folders from the computer go onto the folder shown, a folder row or a folder of the
tree, which then opens; a file dragged alone out of Chromium onto the desktop is
saved there, a PDF with its notes. A folder going to the next keeps showing until
the next has loaded, so the path and the tree stay put.

Notes on a file (f5-2, 2026-10-19) live beside it and never change its bytes. A
file node has its own Yjs room, as a document has, whose `marks` map holds its
highlights (text chosen and a colour from the highlight palette) and strokes
(mouse, finger or pen, a text colour and a width), in the page's own coordinates;
several people annotate live and Ctrl+Z takes back only one's own. Highlighting
and drawing need the edit role; a click on a mark chooses it for removal. Comments
are the documents' threads on a page instead of a tab (`{page, rects}` for chosen
text, `{page, at}` for a point), in the same Comments panel and search. Our SVG
layer lies over each page; pdf.js's own annotation editor is not used, and the
annotations a file came with show as part of it. *Download* and *Open separately*
give a copy with the notes written in by pikepdf (`/api/nodes/<id>/noted`):
Highlight, Ink, and Text with its replies and resolution, each with its own
appearance, an owner-only protection kept; *Download original* gives the bytes as
they came. A file that opens only with its password takes notes in PONISTRA, but
its downloads are the original, as said beside them.

A PDF form (f5-3, 2026-10-20) is filled in the same room: pdf.js draws the text
fields, boxes, radio groups and lists as fields of the page, in our colours, and
the room's `fields` map holds each field's value by its full name (the text, the
state of the box that is on, the option or options chosen) and the text as the
field's own script shows it. Several people fill live, and Ctrl+Z takes back
only one's own: a field's typing and what the scripts reckon of it are one step.
Filling needs the edit role; readers see the values in fields they cannot
change. The file's scripts (number and date formats, checks, sums) run in
pdf.js's QuickJS sandbox in the browser of whoever types, the one place the
browser computes, and what they reckon enters the room as typed. A value filled
in elsewhere reaches the local scripts silently, as committed there, so that the
next local sum counts it; nothing they reckon of it is written again or shown.
Their messages show in the bar above the pages, never in a browser dialog.
Signature fields and buttons that act on nothing pdf.js does are marked and say
why; a form made in XFA alone says it cannot be filled, and a form with both
fills its AcroForm fields. The downloads carry the values with the notes, fields
still fields: pikepdf sets each value, draws single-line text and drop-down lists
as shown, and leaves the reader to draw wrapped or combed text and lists
(`NeedAppearances`); the XFA a form came with is dropped, as readers would
prefer it to the filled fields.

Pages (f5-4, 2026-10-20) are put together into a new file, never in place: a file
has no versions, so its pages stay as they came. *Pages* on the file's bar lays
them out as thumbnails of our own, drawn as they come into view (pdf.js's page
mapper is not used); chosen by click, Shift, Ctrl and Ctrl+A, they turn by
quarters, go, and move by dragging, Alt+arrows or the bar, and the pages of
another file come in after the chosen ones, from PONISTRA or from the computer
(uploaded beside the file first). Nothing is written until *Save as a new file* or
*Extract selected*, Ctrl+Z steps back, and leaving with changes asks first.
Several files chosen in a folder offer *Combine into one file*, with a name and an
order. The server makes the file with pikepdf alone (`/api/nodes/compose`), beside
the file it came from or among the user's own where they may not add to that
folder, as *Make a copy* does: each page with its turn added to its own rotation,
the links and bookmarks whose pages came along (a combined file's under each
file's name), the form fields with their values, a field name met twice taking
`+1`, and the notes in the new file's room; comment threads stay with the
original. A file locked by a password or whose own permissions forbid assembly is
refused, and the button or dialog says why before anything is tried. A folder's
*Download* gives the noted copy, as the file page does.

Scans (f5-5, 2026-10-20) are read where they lack text. Extraction queues a file's
bytes when a page has none, and a second loop in the ASGI lifespan, over Postgres
like the first (LISTEN/NOTIFY, a sweep, a claim that lapses after 30 minutes),
hands them to the `ocr` service: Tesseract in Croatian and English through
ocrmypdf, on a network that reaches only the backend, one file at a time. Pages
with text stay as they are; the others get an invisible text layer (ocrmypdf's
sandwich renderer, as its fpdf2 one drops the text of an upright page a reader
shows turned), and a page Tesseract is sure lies upside down or sideways is
turned upright. The bytes as uploaded never change: the read copy is a blob of
its own, one per original and kept while the original is, and it is what the
file is shown, searched, noted, downloaded and taken apart from; *Download
original* gives the bytes as they came, and a copy that finds no new text is not
kept. While it waits the file page says *Recognising text…*, then opens the read
copy on the page it was at, under a URL that names its bytes, so that a reader
still on the old ones keeps them. Encrypted files (ocrmypdf would write them
without their restrictions) and signed ones (the signature would no longer hold)
are left as they are, and the page says why; a failure is logged and shown with
*Try again*. The migration queued the files already there. Not done: pages that
already carry text, other languages, PDF/A.

Redaction (f5-6, 2026-10-20) takes what is marked out of a new file, never in
place. *Redact* marks the text chosen, a rectangle drawn with the bar's tool,
or every match of the file's find (`/api/nodes/<id>/found`, read by the server
from the bytes it will change). The marks live in the file's room (`redactions`),
shared and hatched until a copy is made; only an editor makes them, and Ctrl+Z
takes back one's own. *Save redacted copy* (`/api/nodes/<id>/redacted`) makes
*Name (redacted)* where a composed file goes (f5-4), from the read copy where
the file was read (f5-5). Under each box every glyph goes, seen or not (an OCR
layer, white text, a hidden layer), and the rest of the line keeps its place;
image pixels are cleared and the rest of the image kept in its own encoding (a
JBIG2 image comes out as plain samples); drawings are cut at the box's edges;
links, notes and form fields the box touches go with their values; the box is
drawn black. The whole copy loses its metadata, attachments, scripts,
thumbnails, private application data, the alternate texts of what went and its
earlier revisions; bookmarks stay, as do the notes and values the boxes miss,
and comment threads stay with the original. pikepdf rewrites the content and
pypdfium2 says which glyph is under a box, by its ink, so that the check counts
what was removed; pypdfium2 then reads the copy, and a character still under a
box means no file is made. What cannot be taken out exactly (text in a font
whose widths cannot be known, an inline or undecodable image, a pattern holding
text) is refused rather than half done. A file locked by a password or whose
permissions forbid changes is refused, the tool saying why first; a signed file
can be redacted, and its signature does not come along, as the bar says. Not
done: replacement text, labels or colours other than black on the box; marking
by pattern (OIB, IBAN), which is an action (A); redaction in place, and of
documents, spreadsheets and presentations; reading Acrobat's redaction
annotations, and our marks in the noted download.

Embedding (f5-7, 2026-10-20) puts a PDF into a document as a block of its own
(`pdf`: the bytes' hash, a title, the first and last page it shows, width and
alignment), a copy and not a link: the bytes are the document's as an image's
are (`DocumentBlob`, which the images' table became), so the file can later be
moved, changed or deleted without the document noticing. *Insert › PDF file…*
and `/` pick one of the folders, starting beside the document, which needs the
right to read it and gives its read copy where it was read (f5-5), or one from
the computer, which goes into the document only and is not read by OCR; a PDF
dropped or pasted goes in the same way, and one copied from another document is
linked to this one by its hash. A file locked by a password or whose permissions
forbid assembly is refused. The editor shows the pages one below another as wide
as the block, each drawn by pdf.js as it comes near the view, and a page breaks
to the next paper page as a table row does; a selected block takes *Pages…*
(from one to another), the width by its handle, the alignment, *Open
separately* and *Delete PDF*. Print takes each page in as it is, vectors and
text (pikepdf lays the page over the place the printed document left for it),
Word and PowerPoint get a picture of each page at 200 dpi described as *Title ·
N*, `.ponx` carries the bytes, and search finds the document by the embedded
text and leads to the block and page. Not done: a live link to the file of the
folders, notes, forms or redaction inside an embedded PDF, a page as a sheet of
its own, and PDFs embedded in imported Word files.

## Document model (D8)

- **One kind.** Every document is the same thing: blocks of text (paragraphs,
  headings, lists), footnotes, images, embedded PDF files and tables. A table
  is a block like any other; a cell holds formatted text (paragraphs, lists,
  marks), as most docx tables are layout, or a formula, either with a number
  format; text that reads as a number or a date in the document's language
  computes as one, and the table can be sorted (D13).
- **Tabs.** A document is an ordered tree of tabs, its chapters, all of that one
  kind. Each tab has its own Yjs room, so only the open tab is loaded; the
  document's own room holds what its tabs share.
  Permissions and versions belong to the document.
- **Outputs.** The document saves as docx and prints to PDF through the page
  view; a table saves as xlsx with its formulas; the slides are the document
  itself, each title, heading 1 or slide break starting a slide, laid out by
  the document's slide template, and save as pptx. Office files come in the
  same way: docx as a document, an xlsx sheet as a table, pptx slides as the
  text of the slides they were with the file's layouts as the template, each import
  keeping its original file beside the document (a `blob` of the document).
  The import of each format arrives with the part it fills: docx with the
  editor, xlsx with the tables, pptx with the slides.
- **Formatting** is marks on text runs inside the Yjs structure. Never markup
  characters in the text (concurrent edits break the pairs) and never offset
  ranges in a table (every keystroke above shifts them). Markdown is only a
  typing shortcut and an import/export format.
- **Styles.** A heading is a block type (title, subtitle, heading 1–4), not
  bold 18 pt. Appearance comes from named styles defined once per document or
  in a shared template; cell styles and slide layouts work the same way.
  The document's theme is a font pair (headings, text) that every style
  inherits (D9). Both live in the document's own room: a map `theme` and a
  map `styles`, one map per style (kind, name, font, size, bold, italic,
  colour, alignment, space before and after, line spacing, numbering), flat,
  with no "based on" chain. The built-in styles (text, title, subtitle, heading 1–4)
  can be changed but not deleted; a block names its own style in its `style`
  attribute or else shows its kind's, which is also where a deleted style
  falls back. A new document starts from the built-in template, and Theme and
  styles… can take both from another document. A version holds the
  document's own state with its tabs. Clear formatting removes marks,
  alignment and indents, and keeps the block type and its style.
  Direct formatting is a fixed set: bold, italic, underline, strikethrough,
  link, colour, highlight, subscript, superscript; a paragraph's are
  alignment, indents and tab stops (D13), while line and paragraph spacing
  come only from a style. Font and size change only through a style; an
  imported docx keeps what it brings. Colour and highlight come from a fixed
  palette stored by name, so the Text view's dark theme shows each in a
  readable shade, paper prints the light one, and a copy to another program
  carries the printed value. An imported file keeps its own colours as
  `#rrggbb` (one equal to a palette colour's paper shade takes its name), and
  the dark theme derives their shade: text lightened, highlights and fills
  deepened, as the palette's are drawn.
- **Addresses.** Every block, cell, slide and shape has a permanent id; links,
  comments, cross-references, search hits and AI citations point at it. The
  readable address is computed from the current structure: `Spec › 3.2 › ¶4`,
  `Offer › Prices › table 2 › D7`, `Offer › slide 5`, `Offer.pdf › p. 3`. Table
  rows and columns carry ids too: `D7` is computed and formulas store ids, so a
  row inserted by one user never moves another user's concurrent edit.
- **Element table.** One row per heading, table, image, PDF and chart, every
  block with text and every node cell: tab, position, block id (plus row and
  column ids for a cell), type, plain text with its tsvector, content (JSONB:
  runs with marks and the block's attrs such as style and level; a cell's
  blocks) and address (JSON: the section its headings number, `1.0.1` when a
  level is skipped, then the paragraph within it, or the table and cell as
  `D7`; the UI words it in its language). What the light cells show is found
  in their grid's rows (`GridRow.words`, D16), searchable as soon as they are
  written; the hit takes the table's address from its element row. A server loop reads it from the tab's Yjs state
  once the tab has been quiet for 3 s, or every 30 s while edits go on
  (`ELEMENT_QUIET`, `ELEMENT_INTERVAL`); it is never edited directly. A search
  hit opens the tab at its block (`?block=<id>`) and flashes it, or at its cell
  (`?block=<table>&cell=C3`), selected and scrolled into view.
- **Charts** (f3-5, Ivo 2026-10-18). A chart is a block of the text (`chart`),
  never in a cell, drawn over a range of a table in the same tab and holding no
  data of its own. Its `range` is a reference as a formula keeps one, the
  table's id and its first and last row and column by id, so it follows the
  table as a formula's range does (D4): a line inserted inside it joins it,
  removing its first or last line shrinks it, sorting keeps its places. Beside
  the range a chart keeps its kind (`kind`: column, bar, line, area, pie,
  doughnut, scatter), whether column, bar, line or area series stack
  (`stacked`), whether its series run down the columns or along the rows
  (`by`), whether the range's first line names the series (`names`) and whether
  the first line across gives the categories, or a scatter's x values
  (`labels`), each decided automatically while unset, its title and whether it
  shows a legend. Combined kinds and a second axis are not drawn. Only the
  server computes: the room that computes the tables reads each chart's range
  out of the computed sheet into the tab's `charts` map, by the chart's id (the
  series' names, the categories, and each value as a number, or none where the
  cell holds no number, and as its cell shows it), and the browser draws what
  it reads, with ECharts' SVG renderer, loaded once a chart appears. Automatic
  names and categories decide as Excel does on inserting a chart: the first
  row names the series when a cell after its first holds text, the first
  column gives the categories when a cell under its first holds text or a
  date, and an empty top left cell makes both; a scatter's first column is
  always its x values. A pie draws the first series, a doughnut each series as
  a ring. A chart whose table or range is gone says so in its place. The
  series take eight hues in a fixed order from `colors/colors.json`, checked for
  colour blindness on both themes, and the chart's text is the document's font. Its
  title is searched as an image's description is. Insert → Chart… opens a
  dialog that puts the chart where the cursor is, over the nearest table before
  it; Chart from the table in a table's menu is an action (D14) that puts a
  column chart just after the table at once, over the selected cells or else
  the whole table above its totals row, and the same dialog edits any chart
  after. An xlsx sheet's charts come
  in after its table, the cells each chart's series refer to made its range; a
  Word chart brings the sheet of its embedded workbook as a visible table just
  before it, or, linked to a workbook outside the file, a table of the values
  it last showed. What a chart cannot keep (a combined kind, a second axis, a
  100 % stack, series that are not side by side, 3-D) is listed in the import
  report. docx and xlsx export write the same model as a real chart (F4).

## Phases

Estimates with agents, made 2026-10-16. Progress, item by item, lives on the
plan board in our production's Ponistra;
this table holds scope and estimates.

| Phase | Content | Estimate |
|---|---|---|
| F0 | Skeleton: compose, health, revision, deploy | 1 day |
| F1 | Users and login, document tree, blob store, versions, the frame and the explorer (D9), permissions, search, Yjs sync (D2) | ~3 weeks |
| F2 | Document editor: blocks, styles, themes and fonts, command registry, toolbar and menus (D9, D13), lists, footnotes, images, links, comments, element table, docx, odt, doc and rtf import | 3–5 weeks |
| F3 | Computing tables: grid, formulas, number formats, sorting, charts, xlsx and ods import | 4–6 weeks |
| F4 | Outputs, the Pages view first: rulers, page setup, headers and footers (D13); then PDF print, docx, xlsx, xlsm and docm export, slides with pptx import and export, PONISTRA's own file (D10) | 3–5 weeks |
| F5 | PDF files: pdf.js view, annotate, forms, merge/split, OCR, redaction, embedding | 2–3 weeks |
| A | Actions (D14): operations on the server, the action registry and runs, proposals, AI with consent, free prompt | 5–7 weeks |
| A6 | Tables our way (D19): totals by choice, the calculated column, the agent beside the document with analysis at scale | 2–3 weeks |
| E | Our own formula engine (D22): Postgres the only place of the grid, a function registry in SQL and Python, Excel's saved values as the measure, xlsx and CSV as streams; IronCalc leaves. Before A6's agent and analysis | 4–6 weeks |
| H | Built-in help (D49): every function in detail, in Croatian and English, the articles held in step with the code by a gate | about 1 week |
| S0 | Proofs for the suite (D15): the whole suite's memory and disk on one host (arm64 builds are an option, see Options), IMAP sync against Gmail and a plain host, an OAuth client for Google, LiveKit with 4–6 people through a reachable port and through an edge | 1 week |
| S1 | Installation and identity: versioned images in a registry, one install command, first-run setup (administrator, domain, TLS), migrations on update, backup and restore with an off-site target, a health page; the directory with groups and passkeys; our production as the first installation (D1) | 2–3 weeks |
| S2 | Chat and meetings: channels, threads, mentions, files from the tree, presence, Web Push; LiveKit with its own TURN, guests by link, recording, a transcript made into a minutes document with tasks; the edge | 4–6 weeks |
| S3 | Mail client: accounts (IMAP and ActiveSync with a password, Google and Microsoft through OAuth), sync with IDLE, the derived copy in search, sending through the account, safe HTML, shared mailboxes, rules and triage as actions, moving mail between accounts | 4–6 weeks |
| S4 | Calendar and contacts: contacts taken from every account into one address book, CalDAV and CardDAV with app passwords for phones, invitations both ways through the user's mail account, free/busy, rooms and resources, tasks | 3–5 weeks |
| S5 | Leaving Microsoft 365: OneDrive files and calendars imported through Graph, mail moved between accounts (S3), a parallel run, then the subscription ends; leaving Google Workspace the same way (D44) | 2–3 weeks |
| S7 | Outside agents (D18): an MCP server over search, reading, writing and the action registry; OAuth with a consent screen and the clients let in listed on the account, each revocable; writes as proposals; mail and calendar tools as S3 and S4 land | 1–2 weeks |

Total ~5½–6½ months for F0–A, ~3½–5½ more for S0–S5 and 1–2 weeks for S7; the
connection with TaskStreamer (former S6) is an option (Options). The order of F2–F5
is D5; where actions come in is D14; the suite follows A, with S0 beside it (D15): S1,
then mail (S3), outside agents (S7, D18) and the calendar (S4) before chat and meetings
(S2), mail first because the calendar's invitations travel through the user's mail
account (Ivo 2026-10-23: "slažem se s rasporedom").
A6 (D19) comes in after S3's step *the mail is ours*, before the rest of S3.

## Open decisions

- **D1: production LXC on mlaka — closed 2026-10-23: a new LXC 104
  `ponistra`** (Ivo: "slažem se sa odlukama"), live as our production since
  2026-11-05 and begun afresh ("idemo na čisto"). Production installs a released version the way
  every organisation does, as the last step of S1, with no path of its own. One app
  per LXC, as with 100, 1011 and 102; unlike Library on 103, no shared file
  tree ties it to an existing guest.
- **D2: Yjs sync server — closed 2026-10-16: pycrdt-websocket** (MIT) inside
  the backend, one language and one process. The ASGI app sends HTTP to Django
  and WebSockets on `/api/collab/<tab>` to the rooms; each update is a row in
  Postgres, and a room's whole state replaces its rows when its last client
  leaves. Verified with the browser library (y-websocket) through the Vite
  proxy: two clients converge, the state survives a backend restart, and a
  client connected through the restart reconnects without losing an edit.
- **D3: document editor core — closed 2026-10-16: ProseMirror** (MIT) with
  y-prosemirror (MIT). The criteria from D8, verified in the spike (f2-1) through
  the real ASGI app and Postgres: the backend reads every block with its id,
  type, attributes and marked runs out of the Yjs state (pycrdt), and writes a
  tab the browser opens and validates against the schema, which is the import's
  path. Lexical's binding is an internal structure Python would have to mirror,
  so it was not built. A table is a block in the text whose cells are nodes
  inside it, each holding blocks as the page does (paragraphs, lists, marks,
  links, images) and naming its row and column ids, plus `to`, the far corner,
  when it is merged; a cell gets its node only once it holds something or is
  merged (f2-9a, 2026-10-17). The grid beside the text in the same Yjs document
  is the row and column ids in arrays. A row added by one user and a column by
  another converge, text stays with its cell when rows move, and undo takes a
  table back together with its grid. Each cell is edited in a view of its own
  whose changes are steps of the document's, so collaboration and undo see no
  difference. Numbering, the contents and the element table read a table's
  cells row by row, and a heading in a cell numbers on as any other, as in
  Word. Copying whole cells gives Word's HTML with its merged cells, and a
  table pasted from Word keeps them. Block
  ids are 12 URL-safe characters; a paragraph keeps its id when it changes type
  or is split (the first part keeps it), and only a copy gets a new one. y-prosemirror 1.3.7 throws when a
  peer deletes the block node selected here (their issue #283, open);
  `frontend/patches/` carries the three-line fix through patch-package until a
  release has it.
- **D4: formula engine — closed 2026-10-17: IronCalc, computed on the server**
  (Ivo: "potvrđujem", then server-only). The grid is ours: FortuneSheet is a
  whole sheet, not a block in a text. Only the backend computes: every table of
  a document is a sheet of one IronCalc workbook (the `ironcalc` wheel, one
  pinned version), live on the server while the document is in use (D16), and
  the server writes the values into the tables' rows, where it is the only
  writer. Browsers read them through the grid socket; export, search and
  versions read the stored values. IronCalc knows 497 functions and Excel's rules
  (`ROUND(2.5;0)` is 3, `0.1+0.2=0.3` is TRUE, text in a range is skipped), so
  an imported xlsx computes as it did in Excel; an evaluator of our own would
  have to find each such rule, and a missed one gives a wrong number, not an
  error. A cell keeps what was typed as its text, read in the document's
  language (`locale` of the document, `hr` by default; the document menu
  changes it and its tables compute again). A cell in its row (D16) keeps
  its formula in pieces, text in the canonical form xlsx stores (English
  function names, commas between arguments, a decimal point) and references by
  row and column id (D8); its number format code; and the value a cell with a
  formula or a format shows and its kind, written only by the server, which
  overwrites any other write. Function names are English in every language (Ivo,
  2026-10-17). The browser sends a formula as typed, in A1, and the server turns
  `A5` into ids in the order the user sees and gives the browser its text; no
  engine ships to the browser and the ids never leave the server. A formula is
  written in the document's language as IronCalc writes it: where decimals take
  a comma, `;` separates arguments and `/` array rows (`=SUM(1,5;A1)`). A
  separator of the other kind or an address outside the table is refused in
  the cell with its place marked, never stored as an error value. A cell with a
  formula shows its value; entering it opens the formula, and a click or drag
  on other cells, where a reference fits, writes their address. While a table
  is in use it shows Excel's headings, column letters above and row numbers
  beside, in room it keeps for them, so that they move nothing; a letter, a
  number or the corner selects whole lines, or writes their address (`B1:B3`)
  into a formula. "Duplicate as values" puts a copy below the table, as Excel
  pastes values: the server types each formula's value as the document's
  language reads it back, with the number format it shows in, and the copy
  takes the next free name (`BOM (2)`). Copying works
  as in Excel: the relative part of an address moves as far as the copy went,
  a `$` part stays, and an address moved out of the table becomes `#REF!`. The
  clipboard carries each value as the cell's text for other programs and the
  formula beside it (`data-formula`). Removing the first or last line of a
  range shrinks the range; a reference to a removed cell is `#REF!`. Each
  entered formula is one undo step. A cell's number format comes from the
  table menu (general, number, whole number, currency, percentage, scientific,
  date, time, date and time, or an Excel code of one's own, written with the
  document language's separators, `#.##0,00` in Croatian), stored in the
  canonical form and written with the language's separators. Date and date and
  time are Excel's built-in short date (14) and date with time (22), which show
  as the document's language writes a date, `15.12.2025.` in Croatian and
  `12/15/2025` in American English, and change with it, as Excel shows them on
  the reader's Windows; a bare `/` in a date code is the language's separator,
  `\/` a slash. A number, date or time typed into a cell with a format shows
  as the format writes it, on the right unless its paragraph is aligned
  otherwise; entering the cell shows it as typed, and typed text stays text. A
  cell keeps its look as Word keeps a paragraph mark's: an empty paragraph
  holds its marks at its end (`endMarks`, read from Word's `w:pPr/w:rPr`), so a
  formula's value shows bold or coloured, what is written into it takes them,
  and a cleared cell keeps them with its alignment. Formatting a range of cells
  reaches the cells that have no node yet. Sorting, ascending or descending from
  the table menu, takes the selected rows, or the whole table under its header,
  by the cursor's column. The server compares the values IronCalc computed as
  Excel does: numbers, text in the language's order (ICU through PyICU, case
  ignored), logical values, errors, with empty cells last and equal ones in
  their order. A first row is a header when its text is bold and the next row's
  is not, or when it is the only text over a column of numbers. Only the order
  of rows changes: a row moves whole, its formulas with it, since they hold row
  ids, while a range over several rows keeps its places, as in Excel; a cell
  merged across rows refuses the sort. The browser writes the order as one undo
  step; two people sorting at once leave each row once, at its first place. A
  spreadsheet (xlsx, or ods and xls made xlsx by LibreOffice) comes in as one
  tab (Ivo, 2026-10-18): each sheet a table under its name (`name`, shown as the
  table's caption), from A1 to the last cell it uses or a formula points at, so
  addresses, `ROW()` and implicit intersection stay as the file has them. A
  reference to another sheet carries that table's id (`table`), the tab's tables
  compute together as one IronCalc workbook, and the workbook's defined names
  are the tab's (`names`, each `{name, pieces, table?}`, with no editor of their
  own yet). A range that runs past a sheet's last row or column is cut at its
  edge. One line of plain text with one look is a light cell, a value in its
  row with no node, so a sheet's thousands of cells do not each cost an editor;
  a cell gets its editor only while it is written in or its content needs one
  (D16), and the canvas draws the others. A sized table (`sized`, as every sheet is) keeps its
  columns' widths in Excel's characters and is as wide as they are;
  a column is drawn with its cells' sides, a character each, less the five
  pixels at seven to a character Excel counts in the width, so it holds the
  text Excel's does. Dragging a column's edge changes that column alone and the
  table grows or shrinks, a double click fits it to its text; any other table's
  widths are shares of the page's width until its first drag. A row is at
  least as tall as its height in points, never cutting its text, as
  Word's "at least": its bottom edge is dragged, a double click lets it go, and
  the import keeps Excel's rows set by hand and Word's row heights (an exact one
  as the least). A table wider than the text column spreads over the pane,
  centred, and scrolls sideways only where the pane is narrower still. Text
  after an apostrophe stays text and shows without it, as in Excel. A function IronCalc does not know
  keeps its formula and shows `#NAME?`. The import compares every value with
  what IronCalc computes for the file as it came and reports the cells that
  differ, the unknown functions, and what a table cannot hold: hidden
  sheets (shown), values an array formula spills, what a
  chart cannot keep, pictures, pivot tables, cell comments, conditional formatting, validation,
  macros and links to other workbooks. IronCalc is ours to patch, not waited on
  upstream (Ivo, 2026-10-18): the backend image builds the wheel from tag v0.9.0
  with `backend/patches/ironcalc/` (the `hr` locale, dates that end in a dot,
  times rounded to the second, which showed 13:45 as 13:44, typed times read as
  numbers, defined names that hold a constant or a formula, xlsx files without
  optional style parts or with absolute targets, a number turned into text as
  the language writes it, `3,25` in Croatian, and dates in the language's own
  form, with the Croatian short date `dd.mm.yyyy.` as Windows writes it rather
  than CLDR's spaced one), as `frontend/patches/` does for y-prosemirror; a
  newer IronCalc takes the patches along.
- **D5: phase order after F1 — closed 2026-10-16** (Ivo: "nastavi prema
  preporukama"): document editor → computing tables → outputs → PDF files. The
  editor is the product; tables and outputs build on it. Imports do not wait
  for F4, each arrives with the part it fills (D8), since without them the app
  starts empty.
- **D6: OCR pipeline — closed 2026-10-20** (Ivo: "ok"). ocrmypdf 17 runs
  without Ghostscript: pypdfium2 rasterizes, and Ghostscript serves only PDF/A,
  which is never asked for; unpaper and pngquant (GPL) stay out too. Verified in
  the `ocr` image. It is a tool service with a queue in Postgres, not Celery
  (f5-5).
- **D7: access from outside — live 2026-10-16, under the name Ponistra since 2026-11-04 (D29)**,
  one row in mlaka's `services.conf` (`both`: Caddy on the LAN, mlaka's tunnel
  from outside). Since 2026-11-05 that name is production's, LXC 104 on mlaka
  (port 80), installed afresh rather than moved from dev, and the dev frontend on
  LXC 210 (port 5190) answers as the dev installation's name. Login and the
  WebSocket session and origin checks came first, so the URL never served an
  open app.
- **D8: document model — closed 2026-10-16**, as in the section above. Ivo
  chose one kind of document, with tabs as its chapters, computing tables as
  blocks, slides made from its headings, uploaded PDFs as files in the tree,
  and direct formatting limited to the fixed set of marks.
- **D9: layout, commands and fonts — closed 2026-10-16.**
  - *Frame.* The same on every screen. A top bar: the path, the view switch
    Text | Pages | Slides, the one search, who is in the document, Share, and
    the user menu (language, sign-out, version). A left panel, full height
    with the logo centred at its top, that follows where you are: the folder tree with the trash at its foot; inside a
    document its tabs and the headings of the open tab, with ≡ bringing the
    whole tree over the screen. The headings come live from the open tab's
    editor, the one holding the cursor marked, and each leads to its block
    (2026-10-17). A tab moves by dragging (onto the top or bottom edge of
    another, or onto its middle to become its last subtab) and by its menu:
    move up, move down, indent under the tab above, outdent after its parent.
    The middle of a folder is the explorer:
    columns name, type, modified, modified by and size, sorted by a click on
    the column with folders first; Ctrl or Shift for several items, then move
    or trash them together; drag onto a folder, in the list or the tree, to
    move, or onto the trash; files dragged in from the desktop upload; double
    click opens; the right click offers the same menu as ⋯. A right panel
    that opens only on request:
    comments, versions, styles. On a phone the panels are drawers and the
    toolbar sits above the keyboard. Surfaces part by tone, not lines: the
    left panel and top bar are one sage-tinted ground, the middle and the
    right panel rounded cards on it, the toolbar a rounded bar inside the
    card. The Text view follows the light or dark theme; the Pages view is
    always white paper. With the suite, a rail of modules sits left of the
    panel (D17).
  - *Addresses* (2026-10-17). A folder, document or PDF is
    `/f|d|p/<title words>-<id>`: the title in plain lowercase words (č, ć → c,
    đ → dj, at most 60 characters), then the UUID as 22 base62 digits
    (`frontend/src/address.ts`). Only the id is read; an address whose words
    have gone stale is replaced in place, so a rename never breaks a link. A
    tab appears after its document's address only when it is not the first,
    the same way under a version (`/versions/<id>`). The browser tab reads
    "<name> – Ponistra". Addresses of the old `/d/<uuid>` form no longer open.
  - *Commands.* Each command is defined once in a registry: id, label, icon,
    shortcut, where it applies (text, table, image, embedded PDF), when it is
    enabled, whether it is on. The toolbar (a fixed part plus a part that
    follows the selection), the "/" insert menu, the context menu, the palette
    (Alt+/, and Ctrl+K outside the text) and the list of shortcuts are views of it. A command the user may
    not run is disabled, never refused after the attempt. No ribbon and no
    menu bar: the rare document commands (save as, print, page setup, theme
    and styles, versions) are in the document's own menu.
  - *Fonts.* As D8 says, the toolbar picks a style, never a font. A template
    brings a theme and styles, the document's theme is a font pair (headings,
    text) that every style inherits, and a style may set its own. One `fonts/`
    directory feeds the browser's `@font-face` and the backend's PDF and
    LibreOffice rendering, so print matches the screen. Office fonts map to
    metric-compatible ones (Aptos, Aptos Display, Aptos Narrow → Intos; Calibri →
    Carlito; Arial, Times New Roman, Courier New → Liberation) and look-alikes
    where none exists (Cambria → Caladea, Georgia → Gelasio, Calibri Light →
    Carlito, Aptos Serif → Intos Serif; Trebuchet MS, Tahoma, Microsoft Sans
    Serif, Segoe UI Symbol → Liberation Sans, the nearest of ours in width), and
    a font an imported file names but we lack shows as substituted, never
    silently. Metric-compatible means measured, not claimed: each pair laid out
    the same 10 695 paragraphs of real documents at 16 and 7 cm in Chromium,
    every face, and a pair counts only where the lines break alike (2.11.2026:
    Intos, Liberation 0 or 1 paragraph in 10 695; Calibri's bold kerns a few
    pairs otherwise, 8 at most; Cambria 6.99 is some 4 % wider than Caladea,
    Gelasio breaks up to 46 otherwise). An export writes the Office font each of
    ours stands for. Fonts the reader's computer has are not drawn in their
    stead: Office keeps Aptos to itself, out of the browser's reach, and a
    twin that kerns otherwise would break lines on that screen unlike print.
    Kerning follows Word, which kerns only from the size a style or a run sets
    (`w:kern`; Aptos templates kern every size, Calibri-era ones none): a style
    kerns or not, a run unlike its style carries the `kerning` mark, and an
    export writes both back. Unkerned, Calibri and Carlito break all 10 695
    paragraphs alike; the browser's kerning had broken up to 558 otherwise.
- **D10: PONISTRA's own file — closed 2026-10-16.** Postgres stays the only
  home of a document; the file is for carrying one elsewhere: to another
  PONISTRA installation, into an archive, to a colleague, with nothing lost.
  Extension `.ponx`, short and in the line of docx, xlsx and pptx (no known
  use; `.scr` is a Windows screensaver that mail filters block, `.scpt` a
  compiled AppleScript), a zip like docx and odt, its `mimetype` entry first and
  stored (`application/vnd.ponistra.document+zip`) as in OpenDocument, so the
  upload knows it by its content: `manifest.json` with the format version,
  `document.json` with tabs, theme and styles, the comments and the people they
  and the proposed changes name (name and email), the exact Yjs state of the
  document's own room and of each tab beside a readable JSON snapshot of its
  blocks, and `files/` with images and the imported original (embedded PDFs
  with F5); versions only when asked for (Save as › PONISTRA with versions). It
  arrives with the outputs (F4), from the same exporter. Coming back, the file
  becomes a new document or tabs after a document's own (Import into this
  document). Its tabs take new ids, so it can come in beside the document it was
  saved from, and the own room's state moves what it keeps by tab to them. A
  person is this installation's user with the same email; one without an account
  keeps their name on their comments and proposed changes. Every state is checked
  against the schema before it is taken in, and a file of a newer format version
  is refused by name. Into a document, as with any imported file, the document
  keeps its theme, and a style, list format or slide layout it has keeps its
  look; the file's versions stay with the document it was saved from, and the
  report says so. Make a copy is the same packing and unpacking on the server,
  without versions: the copy goes beside the original where the user may add to
  its folder, and among their own documents where they may not.
- **D11: permissions — closed 2026-10-16.** A grant sits on any node
  (folder, document, file) and holds for everything below it, and grants only
  ever add: a node below can widen access, never narrow it. No deny and no
  broken inheritance, so who sees a node is always its own grants plus its
  ancestors' grants, and a readable folder never hides a child, so a listing
  needs no filtering per row. Tabs and versions have no grants of their own.
  - Roles: **read** (open, download, see versions; on the WebSocket the server
    drops the client's document updates but keeps its presence), **edit**
    (change content and tabs, create, rename, take versions, restore a
    version, put into the trash and take back from it, move inside the
    topmost folder the user can edit), **owner** (share, move anywhere the
    user can edit, since that changes who sees the node, and delete for
    good). A node can have several owners and keeps at least one.
  - Grantee: a user, a group, or everyone on the installation. Users and groups
    are managed on a Users page that only administrators see, which is also
    where accounts are created from now on. An administrator sees no document
    without a grant. Deactivating a user who alone owns top-level nodes needs
    a successor, who becomes their owner; the dialog shows only how many there
    are, not their titles. A group that alone owns a top-level node cannot be
    deleted, and the last active owner cannot give up a top-level node.
  - The tree: **My documents** holds the top-level nodes I own and what I create
    there. **Shared with me** holds the topmost nodes granted to me whose parent
    I cannot see; their path starts there, and the hidden folders above them
    are never named. Creating inside a shared folder needs edit and gives the
    creator no extra grant. The column calls it **Shared** (people icon), and
    its page switches between *With me* and *By me* (Ivo, 2026-11-02: "kako
    znamo koje smo mi sherali"): by me lists the topmost nodes of my own
    documents that anyone besides me may open, a shared folder once rather than
    every document in it (`/api/nodes/shared?by=me`).
  - The overview. Because grants only add, a folder's picture is small and
    exact: who has access to the folder itself, plus the nodes below it with
    grants of their own, the only places where access differs.
    - The explorer's **Access** column: per row, who has access (initials, or
      Only me, or Everyone) and a mark where the row has grants of its own.
    - **Share** in the top bar and in a row's menu opens the **Access** right
      panel: who has access here and from where (directly, or from folder X),
      then every node below with grants of its own, filterable by person
      (what Ana sees in this folder). Whoever can read sees it; owners change
      the node's own grants there.
    - A change closes the open sessions that lost access or changed role, so
      the client reconnects with its new rights.
  - Every endpoint checks rights through the node's ancestry; file bytes are
    only served through a node, so they follow it. Search (F1) returns only
    what the user can read.
- **D12: search — closed 2026-10-16.**
  Postgres full-text search and nothing beside it: the content is already in
  Postgres, a second engine is a second copy to keep in step (OpenSearch), and
  the rest fail the licence rule (ParadeDB pg_search AGPL, Typesense GPL-3,
  Elasticsearch AGPL/SSPL/ELv2).
  - *Language.* A text search configuration `hr`: `unaccent`, then Snowball's
    `serbian` stemmer, both shipped with Postgres 18 (PostgreSQL, BSD-3).
    Postgres has no Croatian stemmer; the Serbian one reads Latin script and
    folds ijekavian to ekavian. Tested on 18.4: ugovor/ugovora/ugovorima,
    rijeka/rijekama, mlijeko/mlijekom and kuća/kući/kuca each meet in one
    stem, so text typed without diacritics finds text with them. Known misses:
    gradovi ≠ grad, izvještaj ≠ izvještaju. English words match in their exact
    form. No stop-word list, so "ugovor o djelu" matches as a phrase.
  - *Sources.* F1: titles of folders, documents and files, tab titles, and the
    text layer of uploaded PDFs per page, read by pypdfium2 (Apache-2.0 /
    BSD-3; poppler's pdftotext is GPL) and kept per blob, so the same bytes are
    read once. F2: the element table's plain text, comments with them (f2-5). F3: cells,
    by their displayed value. F5: OCR text into the same page table (f5-5). Imported
    originals are not indexed apart (their content is the document); versions
    and the trash are not searched.
  - *Index and query.* A tsvector column with a GIN index per source, titles
    also a trigram index (pg_trgm: typos, parts of codes like "2026-114"). One
    query unions the sources, ranks titles above content, and returns hits
    grouped by node, each with a highlighted snippet and its address (tab,
    block, page). Syntax as in a web search: "phrase", -word, OR; while typing
    the last word is a prefix.
  - *Rights.* Grants only add (D11), so what a user may read is exactly the
    live subtrees under the nodes granted to them: one recursive CTE beside
    `reaching()` in `rights.py`. Search filters by it inside SQL, before
    ranking and the limit, so a page of hits is never short.
  - *Indexing.* Titles as they change. PDF text by a loop in the ASGI lifespan,
    like versions' `keep()`, taking unread blobs with `SKIP LOCKED` and woken
    by the upload, so a PDF is searchable seconds after it arrives. OCR is a
    second such loop (f5-5).
  - *Frame.* The box sits in the top bar between the path and the actions; on a
    phone an icon opens it over the bar. Typing lists the first hits under it;
    Enter opens `/search?q=` with filters (kind, this folder, modified).
    Alt+/ focuses it from anywhere, Ctrl+K wherever the text does not take
    that key for a link (as Word and Docs do): D9's palette and the search are
    one box, documents and the registry's commands.
- **D13: the editor's surface — closed 2026-10-16.**
  - *Import.* One converter in the backend: python-docx and lxml (MIT, BSD)
    read the docx and pycrdt writes the tab's Yjs state in y-prosemirror's
    layout (verified with pycrdt 0.14.9), so a document is ready when its
    upload finishes, with no browser open. LibreOffice headless only turns odt,
    doc and rtf into docx first. The same mapping serves the docx export (F4)
    and pasting from Word. Not mammoth: it drops fonts, sizes and page setup by
    design. Word styles become the document's styles (Heading 1 the heading 1
    block); direct formatting maps to the fixed marks, and an imported font or
    size stays as a mark that Clear formatting removes and the toolbar never
    adds; numbering becomes lists with levels and start numbers, and numbering
    linked to the heading styles their style numbering, with each tab's tally
    written as the editors keep it (f2-8b); tables the
    table block, merged cells kept; images images, charts our charts over the
    table of their embedded workbook, SmartArt its fallback picture; footnotes footnotes; comments ours, an outside author's
    name kept as text; tracked changes come in as proposals with their
    authors and dates (D14 *Review*); the table of
    contents becomes our contents block, page fields the header's fields,
    other fields their last shown result. Each section comes into the same
    tab after a section break, with its own page setup and headers where it
    sets them (D14 *Page setup*).
    Text boxes and shapes are not carried. A bar at the top of the imported
    document says what came and what did not ("Calibri → Carlito"); nothing is
    dropped silently.
    Formatting by hand comes in as styles, decided by code without changing
    how anything shows (Ivo 2026-10-25: the structure shows in the formatting,
    so it needs no step of its own and no AI). The text style takes the font
    and size more than half of the body text shows by hand, an Office font as
    ours (Arial as Liberation Sans). A paragraph that shows exactly as a
    heading style becomes that heading. Any other short line, not ending as a
    sentence or a lead-in does, that shows throughout in one look standing out
    from the text, bold or in a colour of its own at the text's size or larger,
    becomes a heading where that look is larger than the text or where two
    lines or more share it: a level for each look, the largest the first and,
    of one size, the first to come, down to the fourth (as Word's AutoFormat
    takes headings). A heading style no block of the file shows takes the look
    of its lines. Then every mark that only says again what its block's style
    shows comes off, in tables too. A single line that stands out at the
    text's size, a heading or emphasis, stays as it is. Imported into an open
    document, its styles keep their looks and a heading keeps its line's in
    marks; a file of slides keeps its formatting, as a heading there starts a
    slide.
    Built in f2-9c (2026-10-17): Upload files… takes a docx and makes a
    document of it in the folder. The file stays with the document
    (`Node.source`, downloaded from the document's menu), and the report
    (`Node.imported`: substituted fonts, what was not carried by kind and
    count, tracked changes taken as Word shows them) is the bar editors see until one of them closes
    it. A list item counts on as Word counted it: `restart` where Word starts
    again, `continued` where Word's list goes on across other blocks or lists
    (Continue numbering sets it as well); a number Word reaches otherwise is
    listed in the report. Each Word list brings its format (f2-9e); a level
    ours cannot show is listed and keeps the standard form.
    SmartArt holds no picture in the file, so it is listed too.
    Built in f2-9b (2026-10-17): the contents block (Insert → Contents, in
    the text or a cell) lists the headings of every tab to its depth (1–4,
    3 by default), each numbered as its tab numbers it and leading to it
    (at once where the text is read, with Ctrl where it is written). The
    open tab's come from its editor, the others' from `headings` in the
    document's own state, which each tab's editors keep beside its tally.
    The document's page setup (`page`: size as the page lies, margins,
    header and footer distance, different first page, first page number)
    and its header and footer fragments live in its own state, a tab's own
    under `tabs[tab]`; they show with the Pages view (F4). A Word file is one
    tab: each section after the first follows a `sectionBreak`, keeping the
    page setup and the headers and footers it names; one that sets nothing
    of its own and runs on (continuous) goes on in the section before.
    Separate even-page headers are listed. PAGE,
    NUMPAGES, SECTIONPAGES, TITLE and DATE in a header become `field` nodes;
    a TOC field becomes the contents block at its depth (`\o "1-n"`), the
    TOC Heading paragraph above it a plain paragraph.
    Built in f2-9d (2026-10-17): odt, doc and rtf. The upload sniffs them by
    content (an ODF package's `mimetype`, an OLE file holding a
    `WordDocument` stream, read with olefile, BSD; the `{\rtf` header), and
    the `converter` service makes each a docx before the import above:
    LibreOffice Writer headless (Debian trixie, MPL-2.0) behind a small HTTP
    server, with the backend's fonts for the same metrics. It sits on an
    internal network that reaches only the backend (no internet, no
    database), runs as nobody on a read-only image with no capabilities,
    gives each conversion a profile of its own, two at a time, and kills one
    that overruns 120 s; an unreadable file is the import's 422, a converter
    that does not answer a loud 503. Import into this document… (the
    document's menu, editors) takes any of the four and appends its tabs at
    the end of the open document, the first named after the file when Word
    gave it no title. The document's theme, styles and list formats win, as
    in Word; styles and formats it lacks are added, and a tab whose pages
    are laid out otherwise keeps its own page setup. The report is shown to
    whoever imported the file in a dialog and not kept: the file joins the
    document and is not its source. Other editors see the new tabs when
    they next load the tab list, as with New tab.
  - *Toolbar.* One row: undo, redo │ style │ bold, italic, underline,
    strikethrough │ link │ colour, highlight │ lists │ alignment, indent │
    Insert │ comment, then one menu named after what the selection is in
    (Table: rows and columns, merge and split, borders, delete, with sort and
    number format in F3; Image: size, alt text, replace; Note: its numbering;
    header: page number, page count). On a narrow screen the rest goes under ⋯.
  - *Menus.* The document's menu (the title's ▾), by intent: New document,
    Make a copy, Rename, Move │ Import into this document… │ Save as › Word,
    PDF, PONISTRA (.ponx); Excel for a table, PowerPoint for the slides │
    Print…, Page setup…, Theme and styles │ Versions, Access │ Move to trash.
    Insert, on the toolbar and behind "/": image, table, PDF, page break, slide
    break, contents, footnote, horizontal line, special character. The right
    click: cut, copy, paste, paste as text │ comment, link │ the selection's
    own items.
  - *Lists, images, links* (f2-4, 2026-10-17). A list item is a paragraph with
    `list` (bullet, number, check), its level the indent in 1.25 cm steps,
    `checked` and `restart`; numbers are computed (1. / a. / i.) and any block
    that is not an item ends the run, so no list container has to stay
    consistent in Yjs. `- `, `* `, `1. ` and `[] ` start one, Tab and Shift+Tab
    change the level, Enter on an empty item steps out a level, then out of the
    list. Copying gives nested ul/ol; Word's mso-list and the web's lists paste
    back flat.
    Built in f2-9e (2026-10-17): list formats. A format is how a list shows each
    of its nine levels: a number in a form (1, a, A, i, I) between words
    („Članak 1.”, „a)”, „(1)”), led by the numbers above („1.1.”), or a bullet,
    any character. Formats live once in the document's own state (`lists`,
    id → levels, frontend `forms.ts`, backend `content/lists.py`) and an item
    names its format in `format`; a list without one shows 1. / a. / i. and
    • / ◦ / ▪. A format never changes: List format on the toolbar (Word's
    number and bullet library) gives the cursor's level a new form throughout
    its list, lists continued across other blocks included, and keeps a format
    alike only once. Copying carries the format in `data-format`; Word's
    markers and fonts (Symbol, Wingdings) and HTML list types paste as
    formats. The docx import maps Word's levels: numFmt, lvlText around and
    between its placeholders, symbol-font bullets, isLgl. A per-level editor
    of one's own forms is not built. An image is a block: the blob's sha256, alt text, width as a
    share of the column, alignment. `DocumentImage(document, blob PROTECT)`
    keeps the blob from the collector and decides who sees it: only a reader of
    a document showing it, SVG under `Content-Security-Policy: sandbox`. The
    picker, a drop and a paste upload the bytes; a picture pasted from the web
    is fetched by the server, from public addresses only, each redirect checked
    again; Word's local `file:` pictures are refused aloud. Each image is a row
    of the element table with its alt text. A link is a mark: http, https,
    mailto, tel and our own `/d/`, `/p/`, `/f/` paths, anything else dropped as
    it is parsed. Ctrl+K in the text opens the link dialog (text, address, a
    document search), a popover under the link opens, edits or removes it, a
    typed address becomes a link, and "Copy link to this place" gives the block's
    address, or in a table the selected cells'.
  - *Numbered styles* (f2-8b, 2026-10-17). A style can number its blocks: a
    form (1, a, A, i, I), text before and after it, and for heading 2–4 the
    numbers of the headings above (1.1.). Each heading level and each other
    style counts on through the tabs in reading order, and a heading starts the
    levels below it again; a list item shows its list's number, never a style's.
    Restart numbering at 1 and Continue numbering, in the context menu of a
    numbered block or list item, set its `restart`, which is also how a tab
    starts from 1 (on its first heading). The number is shown beside the text,
    never written into it; a copy carries it as text, which a paste back here
    drops. The editors of each tab keep its tally (every heading level and
    style, numbered or not, so numbering turned on later counts on rightly
    without the other tabs opened again) in the own room's `numbers` map, as with note counts, and the element table
    takes its numbers from the same tallies: a numbered block's text leads with
    its number and its address holds it (`number`, and its section's `heading`),
    so search points by the numbers the document shows. Theme and styles…
    numbers every heading 1., 1.1., 1.1.1. with one tick.
  - *Footnotes and endnotes* (f2-4b, 2026-10-17). A note is an inline node
    `footnote` (`kind` foot or end, its own `id`) holding the note's text and
    marks inside the paragraph where its mark stands, so it moves, copies and
    undoes with that text and no reference has to stay consistent in Yjs. The
    mark is a computed superscript number (1, 2… footnotes; i, ii… endnotes).
    The Text view lists the tab's footnotes under its text, then its endnotes;
    the Pages view (F4) sets footnotes at the foot of their page and a tab's
    endnotes after its text. A note's text is edited in that list by an editor of
    its own whose changes are steps of the tab's document, so collaboration,
    undo and the toolbar's text commands work as in the text, and the toolbar
    adds the note's commands: back to the text (Esc), turn into the other
    kind, delete, numbering. Insert › Footnote or Endnote puts one at the
    cursor, on the word before any spaces typed ahead of it (they stay after
    the mark), and opens it; a click on the mark opens it, a click on its number
    goes back. Numbers run on through the tabs: each client writes its tab's
    counts into the document's own room (`notes`), and a tab may restart them
    at 1 (`tabs`). Copying gives Word's footnote HTML (`mso-footnote-id`),
    Word's and LibreOffice's notes paste back as notes, and plain text writes
    [1] at the mark and the notes after the text. Each note is a row of the
    element table (`footnote`, `endnote`) at its paragraph's address, so search
    finds it and opens it in its list.
  - *Comments* (f2-5, 2026-10-17). A comment is a thread on a stretch of a
    tab's text: `Thread(tab, anchor, quote, resolved_at, resolved_by)` and its
    `Comment(author, body, edited_at)` rows in Postgres, never a mark in the
    text, so they are neither in the Yjs state nor in versions. The anchor is
    two Yjs relative positions: the start before its first character, the end
    after its last (assoc −1), so text typed at either edge stays out and the
    stretch follows every edit, local, remote or undone. When its text is
    gone, the thread keeps its quote (up to 500 characters) and says so; undo
    brings the stretch back. Anyone who reads may comment; an author edits and
    deletes their own comments, the last one taking the thread with it; an
    editor resolves and reopens threads. Comment (Ctrl+Alt+M, also where that
    chord is AltGr) is on the toolbar and the right click; a reader, who has no
    toolbar, uses the right click. A note's text cannot be commented. The
    Comments panel lists the tab's open threads in the order of the text and
    shows resolved ones on request; a click on a highlight opens its thread,
    and resolving it closes it. `?panel=comments&comment=<thread>` opens one.
    Changes reach everyone with the document open through the server's
    presence in its own room (`comments`, a counter), so nothing is stored or
    versioned; a client refetches the threads on it and when its room is back.
    Search finds comments (`comment` source) and opens their thread. Word's
    comments come in with the docx import and go out with the export (f2-9,
    F4).
  - *Views.* Text: no paper and no ruler, a column of readable width (44 rem)
    that follows the theme; a table wider than the column takes the whole
    pane, and a narrower one keeps to the text's left edge. Pages: a grey field with white pages to scale, zoom
    (100 %, page width), the rulers, headers and footers. Each reader picks
    the view and zoom beside the toolbar, kept in their browser: the view for
    each document, a document they have not chosen one for opening in its
    slides when it came from a presentation, else in the view they chose last.
  - *Page setup.* Paper (A4 by default, A3, A5, B5, Letter, Legal, custom in
    cm), orientation, margins (Normal 2.5 cm, Narrow 1.27 cm, Wide, custom),
    header and footer (distance from the edge, different first page, fields:
    page number, page count, title, date), first page number. The document
    holds the default and a tab may override it. The dialog (document menu,
    F4 2026-10-18) edits the setup the tab follows: the document's, for every
    tab without its own, or the tab's own, which starts as a copy of the
    document's headers and footers; going back to the document's drops the
    tab's own. The document's first page number is its first tab's; a later
    tab numbers on unless it has pages of its own that start again. Margins
    that leave less than 2 cm of text either way are refused.
    A section break (Insert, 2026-11-02) starts a section of the tab on a
    new page: what it sets itself is kept under `tabs[tab].sections` by the
    break's id, its page setup and each header or footer it names (empty is
    blank); what it does not set it takes from the section before, the setup
    without its first page number. With the cursor after a break the dialog
    sets that section's pages, its own or the section before's; the header
    menu links a header or footer to the section before, or gives the
    section its own, starting as a copy. On screen each page stands centred
    on the widest and a section's text keeps its own margins; in print each
    section is printed on its own paper. A section that starts its own page
    numbers restarts within the tab; the next tab numbers on from the tab's
    count of pages. Word's sections come in and go out the same way.
  - *Headers and footers* (F4 2026-10-18) are written on the page itself, in
    the Pages view: a double click in a page's header or footer zone, or
    Insert → Header / Footer on the cursor's page, opens its own editor over
    the part's fragment, with the text dimmed behind it; Insert then offers
    the fields, and Escape or a click outside closes it. A part taller than
    its margin pushes the text down (up for a footer), as Word does; with a
    different first page, the first page has its own pair, empty until written.
  - *Rulers*, in the Pages view only. Horizontal, in cm with a decimal comma:
    dragging the grey margin changes the tab's page setup; the selected
    paragraphs' indents (left, first line or hanging, right); tab stops (left,
    centre, right, decimal), added by a click and removed by dragging them
    off. Vertical: top and bottom margins, the header and footer zones. Snaps
    to 0.25 cm; Alt drags freely. Built 2026-10-18: a paragraph keeps its
    left, first-line (negative where it hangs) and right indents in cm as a
    docx gives them, a numbered one lays out as its number does, and a list's
    item moves a level at a time. The margin is grabbed between the indent
    markers, as in Word; arrow keys move a focused marker.
  - *Notes on pages* (F4 2026-10-18). A footnote stands at the foot of the
    page its mark is on, under a short rule, and the text on that page leaves
    it room: a line whose note no longer fits goes over with it, as in Word.
    A tab's endnotes follow its text, breaking between notes, the rule going
    over with the first. They close the tab rather than the document, after
    its last section, because the Pages view shows one tab at a time and the
    PDF prints what it shows; each note stays editable where it stands.
  - *Tab stops* (F4 2026-10-18). Tab writes a tab character (in a list it
    still moves the item a level). A paragraph keeps its stops in cm from the
    margin, each left, centre, right or decimal (on the document language's
    separator), with an optional dot, dash or underline leader; past them run
    Word's defaults every 1.25 cm, and a hanging first line stops at the left
    indent. The ruler's corner cycles the kind a click adds; a stop's menu
    changes its kind and leader; dragging it off the ruler, or Delete on a
    focused stop, removes it. Tabs… (the right click, the command search and
    a stop's menu) is Word's Tabs dialog, for the keyboard as well: the first
    selected paragraph's stops, set and cleared by position, then done to
    every selected paragraph as changes, so each keeps its other stops; a
    stop stands between the margin and the line's end. A docx's stops join
    their style chain (`w:val="clear"` takes one away). The browser lays a
    tab out as an inline box the editor widens once the line is measured, so
    they show the same in the Text and Pages views, headers and footers
    included.
  - *Phases.* The Text view, toolbar, menus and imports come with the editor
    (F2), the import already keeping page setup, headers and footers. The
    Pages view, rulers, page setup dialog and header editing come with the
    outputs (F4): pagination is the largest piece of work and no editor core
    has it.
  - *Pagination* (F4, 2026-10-18). The browser lays the tab out as one
    column the page's text width; the editor measures its blocks, and for a
    block crossing the page's foot its lines or table rows, and a pure
    function (`frontend/src/editor/pages.ts`) decides where pages break: two
    lines at least at a page's foot and head, a heading, title or subtitle
    kept with what follows, a table between rows and never inside a merged
    cell, a page break block starting a page, a block taller than a page
    standing at its head. Each break is a transparent gap of the remaining
    page, the margins and the grey between pages, as a widget between blocks
    or at a line's start and as a row in a table, so the text stays one
    editable flow; the white pages, headers and footers lie behind it. The
    layout is redone after every change, from measurements without the gaps,
    and only a different one is shown. A page break is a block of its own
    (`pageBreak`, Ctrl+Enter); Word's page breaks and "page break before"
    come in as such blocks, splitting a paragraph where one falls inside it.
    The page counts each tab's readers lay out are kept in the document's
    own state (`pages`), so a header's page number goes on through the tabs
    and its page count covers them all. The server keeps them for tabs nobody
    lays out (F4 2026-10-19): a loop in the ASGI lifespan, beside versions'
    `keep()`, has the `printer` count every tab's pages on the print page
    (`POST /pages`, from its `body[data-pages]`) at once for a document never
    counted, else once its changes have been quiet for 10 s or the earliest
    uncounted one is a minute old, in a session opened for the count as its
    last editor who may still read it (else its author) and closed after.
    It runs in the backend's process because the rooms do: the counts go in
    as a client's edit, and only where they differ, so a recount that finds
    them as they were writes nothing. Counts run one at a time beside the two
    readers' print slots, so a count never keeps a reader waiting. A tab not
    counted yet is new and empty: one page.
  - *Print* (F4 2026-10-18). Print… in the document's menu prints every tab,
    in reading order, through the browser's own dialog. The document's print
    page (`/print/<document>`, outside the app's frame) reads each tab's saved
    state (`GET /api/tabs/<id>/state`) and lays it out as the Pages view does,
    read-only, its pages edge to edge with no grey between them, so the
    browser's pages fall where the tab's do; the paper is taken in whole CSS
    pixels, as Chromium breaks printed pages, or each page's text would creep
    up by the fraction. A tab on other paper prints on a named page of its
    size. Page numbers and the page count run on through the tabs from the
    print's own layout, a tab never opened on pages included. The page is
    laid out in a frame over the document, unseen, and tells it when its
    pages have stopped changing with their fonts and images in
    (`body[data-printed=ready]`); then the frame prints.
    Save as › PDF (`GET /api/nodes/<id>/pdf`, readers) hands the same page to
    the `printer` service: Chromium headless (playwright-core, Apache-2.0,
    driving Debian's headless shell) opens it with the reader's session cookie, in the
    document's time zone, waits for the ready flag and saves it at its CSS
    page sizes, a hundred pages at a time (`body[data-range]`), which the
    backend joins. A table on the print page keeps only its rows' heights,
    measured a few hundred rows at a time, and draws its rows on the pages
    being saved, each page's rows a table placed where its page gap leaves
    it: laid out whole, Tracking's 28,700 values took Chromium past 2.7 GB
    and the printer's renderer was killed (2026-10-21); now 0.75 GB to count
    its 997 pages and 1.6 GB to save them. Its network is internal and
    reaches only the frontend and the backend; it runs read-only with no
    capabilities, each print in a browser context of its own, two at a time
    beside one count, in 4 GB, 120 s at most for the page to be ready; a
    printer that fails or does not answer is a loud 503
    (`printer_unavailable`), and one that ran out of memory says so in the
    backend's log.
  - *Save as Word and Excel* (F4 2026-10-19). `GET /api/nodes/<id>/docx`
    writes each tab, and each section of one, as a Word section on its own
    pages, with its page setup, headers and footers (a first page's where it
    has one; a later section only those it sets itself) and page numbering;
    a tab's title has no place in Word. The document's styles and list
    formats become Word's, and every list and numbered style counts as the
    editor counts it: Word's numbering starts anew wherever its own count
    would differ. Tables keep widths, heights and merged cells and show what
    their cells show (a formula's value, not the formula); images keep their
    share of the text width, photos turned upright, WebP and AVIF as PNG, an
    SVG beside a PNG the `printer` draws of it (`POST /png`, no scripts, no
    network). Notes, page, title and date fields, the contents (which Word
    fills with page numbers on opening) and comment threads with replies and
    resolution go over; a thread whose text is gone stands at the start of its
    tab. An image no reader can open is a loud 422 (`unreadable_image`).
    `GET /api/nodes/<id>/xlsx` makes a sheet of every table through the tabs,
    computed by IronCalc. docm, xlsm and pptm give a document imported from a
    file with macros its original VBA project back.
  - *Charts in Word and Excel* (F4 2026-10-19). Both exports write a chart as
    Office's own (DrawingML) from the same computed workbook: each series refers
    to the cells of its table's sheet and carries what they show, in the editor's
    colours (paper shades) and the document's font. In Excel a table's charts
    stand on its sheet right of it, one below another, as wide as the tab's text
    (rows of no height of their own counted at their least, so charts never
    overlap). In Word a chart stands across the text with the whole workbook
    embedded, so Edit Data opens its cells with their formulas; coming back in,
    it brings that sheet as a table of its own, as any Word chart does. A chart
    whose table is gone goes to Word without series and stays out of Excel.
  - *Slides* (F4, Ivo 2026-10-19: "slažem se sa svim prijedlozima"). The D14
    filter on pptx: what a deck needs so that its look survives import and
    export goes into the model; free placement does not, since a canvas of
    placed shapes is a second editor against one kind of document (D8).
    - *A slide* is a stretch of the tab's text: each title, heading 1 and
      slide break (`slideBreak`, Insert → Slide break) at the text's top
      level starts one, and what comes before the first is a slide when it
      holds anything. The block that starts a slide carries its `layout` (a
      layout's id, null to choose by content) and `hidden`; giving the first
      slide a layout when nothing starts it puts a slide break at the tab's
      start. A column break (`columnBreak`) sends the text after it into the
      layout's second body. Speaker notes are paragraphs marked `speaker`, as
      a list is paragraphs marked `list`, so no container has to stay
      consistent in Yjs: the Text view shows a run of them as one toned box,
      Slides under its slide, and Pages, print and Word leave them out, as
      they leave out both breaks.
    - *The template* is the document's, in its own state (`slides`): the
      slide's size (16:9 by default, 4:3, custom in cm) and its layouts, flat
      as styles are, each with its kind (title, content, two contents,
      section, title only, blank), background (a colour or an image), the
      shapes drawn behind the text (images, rectangles, ellipses, lines,
      fixed text, the slide number, the date) and its boxes: title,
      subtitle, body, second body, each with its place in cm, font (the
      theme's headings or text font, or a named one), size in points with
      one per list level for the body, colour, weight, alignment and where
      the text sits (top, middle, bottom). A document without layouts of
      its own lays its slides out by the built-in ones in
      `schema/slides.json`, which the editor and the backend both read, with
      the layouts' JSON Schema. A slide without a layout takes the template's
      first of its kind: a title makes a title slide, a heading 1 alone a
      section, a column break two contents, a heading 1 and more a title and
      content, and a slide break without a heading a blank one. Content a
      layout has no box for goes where the built-in layout of its kind puts
      it, so a slide never loses text by a change of layout.
    - *The Slides view* is the same editor as Text and Pages: each slide's
      blocks are placed in its layout's boxes, the slides one below another
      at the pane's width, the layout's background and shapes behind them,
      its notes under each slide. Text that overflows its box shrinks to fit,
      as PowerPoint's autofit, by its steps (92.5 % down to 40 %), spacing
      included; what still overflows at 40 % is outlined. The box's look
      (font, size per list level, colour, alignment, anchor) is the
      template's; a block's own alignment and its marks stay its own. A box
      of the layout with nothing written shows its prompt; a click there
      starts its text (a slide break becomes the slide's heading 1, the
      second column starts with a column break) and keeps the layout the
      slide shows, so writing does not change it. All the editor's work
      (co-editing, comments, proposals, actions) goes on on the slide
      unchanged. The toolbar's Slide segment picks the cursor slide's layout
      (by its content, or one of the template's), hides it and sets the
      slide size (16:9 or 4:3, the built-in layouts stretched to it).
    - *Presenting* (the toolbar's Slide segment and the document's menu:
      from this slide or from the start) shows every tab's slides in order
      on the whole screen, numbered on through the tabs as the Slides view
      numbers them, the hidden ones skipped: arrows, space, Enter, Page Up
      and Down, N and P, and a click go on and back, Home and End to either
      end, a number and Enter to that slide (hidden or not), Escape ends;
      after the last comes a closing screen. A strip that shows when the
      mouse moves goes back and on, opens the presenter's window, takes the
      whole screen again and ends the show. The presenter's window, in the
      same browser, shows the current and the next slide, the notes, the
      time since the show started (paused, resumed and restarted there) and
      the clock; it moves the show by the same keys and its buttons, and the
      show and the window keep each other in step over a BroadcastChannel.
      Leaving full screen ends the show, except while the presenter's window
      opens (Firefox leaves full screen then); the page under the show is
      out of reach until it ends, and the cursor is back where it was.
    - *pptx both ways* through the OPC layer of the python-docx already used
      and lxml, as docx is written (python-pptx would add nothing that
      layer lacks), on the backend. Save as › PowerPoint writes every tab's
      slides, each tab a PowerPoint section, the template as one master with
      its layouts (each layout's boxes its placeholders, its slide number
      and date PowerPoint's own fields, which its header and footer
      settings give a new slide), the text in its placeholders with
      PowerPoint's autofit, at the scale the Slides view shrank it to, since
      PowerPoint does not shrink text again before it is edited: the printer
      lays the Slides view out in the reader's session and measures each
      box's fit and each block's place, so the file matches the view.
      Around a picture, table or chart a box's text goes in shapes of its
      own where the view shows it, at its shrunk sizes; the objects where
      the view shows them, charts as PowerPoint's own over their workbook
      (IronCalc's, as in Word); lists as PowerPoint's bullets and numbers
      where its schemes have the form, else the number written out; notes
      as notes, hidden slides hidden, and proposals as the text before
      them. Slides measured other than the document is now are refused
      (409). The import makes a tab of each section (slides in none a
      first tab of their own); a title slide's title its `title` block and
      its subtitle `subtitle` blocks, any other slide's title its heading 1,
      a slide without one a slide break, that block keeping the slide's
      layout and whether it is hidden; its body and other text in reading
      order, top to bottom and left to right, a shape lying inside a box of
      its layout flowing in that box; its pictures, tables and charts (over
      a table of their data, as from Word) as blocks, a second body after a
      column break, its notes as speaker notes. A placeholder is its
      layout's of the same index, or, given none (as LibreOffice writes
      them), the first of its type, the column it stands in deciding
      between two. The file's layouts, each layered over its master, become
      the document's template: their boxes and the look of their text (bold
      and italic always stated, so a box decides them as a placeholder
      does), the shapes the master and layout draw behind the slides, their
      backgrounds, and the slide number, date and footer the slides laid out
      by a layout show, or, for a layout no slide takes, its header and
      footer settings give. Imported into a document, the layouts join the
      document's own, after them, stretched to its slide size. Lists come as
      ours, sharing the formats the document has, and a number ours do not
      count to (a list started at 3) is reported; the theme's fonts become
      the document's theme. Positions of shapes outside the boxes, SmartArt,
      video and sound, shapes other than rectangles, ellipses and lines,
      fills other than one colour or a picture, animations, transitions
      that do anything, comments and a slide's background other than its
      layout's are not kept and the report counts them; the original stays
      with the document. odp and ppt come through the converter as pptx
      (LibreOffice keeps no sections), pptm, potx, potm, ppsx and ppsm as
      pptx, their macros' source shown to read, as from Word and Excel.
- **D14: actions — closed 2026-10-19** (Ivo: "slažem se sa svim"). Office
  compatibility is a contract on the document model, not on the interface:
  whatever docx, xlsx and pptx carry, the model holds and maps both ways, but
  the way of working is our own. Every Office feature passes one filter: if the
  model must carry it so that import and export lose nothing, it goes into the
  model and its mapping; if people do it by hand every day, it is a command
  (D9); everything else, which Office does with a dialog or a wizard, is an
  action and gets no dialog of its own.
  - *Actions.* An action is a named intent on a target (selected text, a
    table, cells, a tab, the document, a folder), its few parameters asked in
    place. How it is carried out is chosen per action and the user does not see
    which: our own code wherever the rule can be written without understanding
    language (clean a table's data, totals and grouping, a chart from a table,
    slides from headings, a template merged with a table, the difference
    between two versions); a model that decides and code that
    carries out where the input is unclear but the result is known operations
    (a search the model turns into filters, a vault item it files into a
    folder); a model alone where text is to be
    understood or written (summarise, rewrite, translate into a new tab, pull a
    contract's data into a table, describe what a version changed). Code first,
    a model only where code cannot. The backend defines each action (id,
    target, parameters, how it runs, how it is reviewed, whether it needs AI);
    the frontend adds them to the command registry, so they come through the
    palette, the context menu and "/", their labels in `frontend/src/i18n/`.
  - *Operations.* Actions, the model and the importer change a document
    through one layer of operations in `apps/content` (insert a block at an
    address, set a style or mark, write cells and formulas, insert a table,
    move, delete a range, open a tab), checked against the schema and applied
    in the tab's room as one transaction marked with its run (A1, Ivo
    2026-10-19: "slažem se").
    - *Schema.* `schema/schema.json`, mounted at `/schema` as `colors/` and
      `fonts/` are, holds the nodes and marks as ProseMirror writes them
      (content, groups, flags) and for each attribute its default and a JSON
      Schema of the values it may take, shared definitions under `$defs`; the
      default is always allowed. The editor's `schema.ts` builds its schema
      from it and adds only how each node reads from HTML and draws itself;
      `schema.d.json.ts` beside it, derived by vitest, gives TypeScript the
      lists' exact values. The backend reads it through prosemirror-py
      (BSD-3-Clause, a port of ProseMirror's model), so a node is checked by
      the editor's own rules, and its attributes through jsonschema (MIT),
      with ECMAScript's meaning of a closing `$`. The editor checks nothing it
      receives: what comes through Yjs is sanitised where it is drawn. The
      importer writes a tab's content and defined names, and the headers and
      footers of its pages, through the same layer, checked as a run is: an
      import whose content the schema refuses fails. References to `$defs`
      are put in place once, when an attribute's validator is built.
    - *Addresses.* An operation names blocks only by their permanent ids (D8):
      before or after a block, at the start or end of a tab, in a cell by its
      table, row and column ids; never a position or an index, which another
      user's typing moves. A text range inside a block is counted in the
      characters of the block's text when the run starts; a selection from
      the browser comes as Yjs relative positions, as comments anchor.
    - *Transactions.* A run is one transaction per room: its operations are
      carried out on a copy of the state and checked against the schema, and
      only then does one update, marked with the run, reach the room. A Yjs
      transaction cannot be taken back, so a run that fails any check changes
      nothing and fails openly. A model's run (A4) writes each tool call as
      its own transaction under the same mark, so the room sees it working,
      and undo takes them together. A run over several tabs or a folder has
      one transaction per room, Yjs having none across documents, the
      document's own room first, and records each room it changed
      (`RunChange`); a room that refuses, or changes that cannot be recorded,
      take back the rooms before it.
    - *The operations* (`apps/content/operations.py`) are JSON, the same for
      an action's code and a model's tool call, each checked first by its
      own JSON Schema there, from which A4 gives the model its tools: insert
      blocks (ProseMirror JSON) at an address, set a block's type and
      attributes, put a mark on a range or take it off, replace a range's
      text, make a table from rows of values, write cells, add rows or
      columns or take them out, put rows in an order, move or delete a run
      of sibling blocks; in the document's own room, set a style's font and
      size;
      opening a tab is a row of its own, not a room's change. Lines taken out
      go as the editor takes them out: a merged cell keeps its slots in the
      lines left, with its formula and number format, and a range whose first
      or last line goes keeps the rest, in every formula, name and chart;
      rows put in an order keep a range over several of them on the same
      places, and a merged cell across rows refuses it. A
      cell holds what one types into it in
      the document's language, a number or a truth value written as that
      language types it; a formula comes apart, in the canonical form xlsx
      stores, its addresses in its own table or after another's name, and
      one reaching past a table's edge or naming no table is refused, where
      the importer cuts it at the sheet's edge. A value written into a cell
      of its own keeps the cell's look, as the editor writes it. Within a run,
      a later range is moved by the run's earlier replacements in the same
      text, and one overlapping them is refused. An image an operation shows
      must already be the document's. A run on a tab nobody has open opens
      its room for the change and leaves it once its tables are computed
      again, so a stored tab never holds stale values.
    - *Undo.* pycrdt's `UndoManager` (0.14.9) takes back exactly one run's
      changes and keeps what others wrote meanwhile (tried 2026-10-19, live
      and on a state loaded again). The run keeps its insertions and
      deletions (`IdSet.encode`), so its undo outlives the room's closing and
      the backend's restarts; for what it deleted to come back, the rooms of
      tabs and documents keep deleted content (`skip_gc`). The price is a
      state that holds all text deleted since; the alternative, a run keeping
      what it deleted to insert it again, would repeat Yjs in our own code and
      lose the comments anchored in that text. Versions keep no deleted
      content: restoring one moves the tabs to fresh rooms, and a run is not
      taken back from a tab that has left the room it changed. Taking back
      gives its own change, which taken back does the run again; a run whose
      change is already gone is refused.
  - *Runs.* Each run is an `ActionRun`: who, which action, the target's
    address, parameters, state, duration, and for a model the model that
    answered, the tokens it read and wrote (their count, never a copy of the
    text), who agreed, this once or for the document, and what it cost. While
    it runs it shows in the room as a
    participant: the server's presence in the tab's room lists it by its id,
    with the action and who started it, and the editor shows it at the foot
    of the page. An action over a folder goes through its documents as the
    items of a queue in Postgres, in the backend's own process (*Background
    work*).
    - *Registry.* `apps/actions/registry.py` defines each action once: its
      target's kind, the JSON Schema of its parameters, how it is reviewed,
      whether it needs AI, and the code that plans its operations. A plan
      reads what it needs from the room and computes off the event loop, as
      sorting does, and hands back what builds the operations from the state
      the room holds when they are carried out, so another user's typing
      meanwhile shifts no address; a table changed past what the plan can
      follow refuses the run. `GET /api/actions` lists them, and the editor
      adds each to the command registry in its target's group, labelled by
      its id in `frontend/src/i18n/`; an action without a label there is an
      error, not a missing command. A run is `POST /api/tabs/<id>/runs`; the
      run done is offered back with Undo action (`POST /api/runs/<id>/undo`),
      which takes its change back once and leaves what others wrote since.
    - *Totals* (`table.totals`, A2) adds a row below a table's data that
      subtotals each column holding only numbers, with Excel's
      `SUBTOTAL(109, …)` so the subtotals of a later grouping are not counted
      twice, in the number format most of the column shows in, labelled in
      bold in the first other column in the document's language (as Excel
      labels its total row). Run again, it covers the rows the data has by
      then. That row is recognised by its formulas, the way Excel's total row
      is: sorting a table leaves it last.
    - *Column total* (`table.total`, A6) runs on the column the cursor is in
      and writes into the totals row's cell under it the function chosen, as
      Excel's total row offers them: sum, average, count of numbers, count of
      values, minimum or maximum (`SUBTOTAL` 109, 101, 102, 103, 105, 104) or
      nothing; a column holding other than numbers offers the count of its
      values alone, the others being disabled in the menu. The row is made
      below the data when the table has none and taken out with its last
      subtotal; it is recognised by any of SUBTOTAL's 101–111 over its own
      column, so a workbook's total row of averages is one too.
    - *Clean* (`table.clean`, A2) trims the whitespace around each cell's
      text and collapses it within, as Excel's TRIM does, makes the numbers
      of the table's data that are kept as text numbers (an apostrophe before
      them, spaces between their digit groups), and takes out the rows and
      columns that hold nothing. A leading zero or a letter marks a code
      (an article's number, a postal code), which stays text; a merged cell,
      a formula, or a reference that points at a line alone keeps its line,
      so cleaning never leaves a #REF!. A table with nothing to clean says so
      instead of running empty.
    - *Group* (`table.group`, A2) runs on the column the cursor is in, as
      sorting takes it, so its one parameter is asked by the place: it sorts
      the data by that column and puts below each run of one value a row that
      subtotals every other column of numbers, labelled in bold with the
      value ("Vijak ukupno", as Excel's Subtotal labels it in the document's
      language), and below them all the totals row, which `SUBTOTAL(109, …)`
      keeps from counting a group twice. Run again, by any column, it first
      takes out the groups' rows it wrote before.
    - *Chart from the table* (`table.chart`, A2) runs on the selected cells,
      or else the table the cursor is in, and asks nothing: a column chart
      just after the table, over those cells or the whole table above its
      totals row, its series down the columns unless the range is wider than
      tall, names and categories decided as on inserting one. What Office
      asks before, the chart's own dialog changes after.
  - *Review* (A3, Ivo 2026-10-19: "slažem se s prijedlozima"). Structure,
    formatting and tables apply at once, with Undo action. Text a model
    writes comes as proposals the user accepts or rejects. A proposal lives in
    the document model (`schema/schema.json`), not in a list of operations
    beside it: such a list cannot carry Word's tracked changes faithfully, and
    its anchors drift under others' typing. Inserted and deleted text carry
    the marks `insertion` and `deletion` ({id, author, date}); a formatting
    change keeps the formatting it replaced; a paragraph's end (Word's
    paragraph mark), a block such as an image, and a table's row carry them as
    attributes of their node, so a whole paragraph or row comes and goes with
    them. That is Word's `w:ins`, `w:del`, `w:rPrChange` and `w:pPrChange` one
    to one, and Yjs syncs them as any other content. The model writes through
    the operations with the flag "propose"; Accept and Reject are operations,
    each a run with Undo action. People propose too: in the Suggesting mode
    ("Predlaganje") typing and deleting become the same marks, so a user
    answers Word's tracked changes with their own. Word's tracked changes come
    in as proposals and go back to docx as tracked changes (D13). Built in A3
    (2026-10-19): the model, Accept and Reject at the cursor (a popover with
    the proposal's kind, author and date), in the toolbar and the context
    menu, and all of a tab's at once; the docx import brings `w:ins`, `w:del`,
    their moves, `w:rPrChange`, `w:pPrChange` and a row's change as proposals,
    the changes next to each other by one author at one time as one proposal,
    as Word shows them. What a proposal cannot hold (a table's, a cell's or a
    section's properties, a cell inserted or merged) and the changes in
    headers and footers, which live in the document's own state outside the
    tab's operations, the import takes as Word shows them and counts in its
    report. The docx export writes each proposal back as Word's tracked
    changes with its author and date: text, notes and fields inserted or
    deleted, a paragraph's end, a picture, chart, page break or table of
    contents proposed whole, a proposed row, and a formatting change keeping
    the marks or the block's type, list and layout it replaced. The
    Suggesting mode is a toggle in the toolbar's Proposals segment, for the
    text, its tables, notes and cells: what the user writes is proposed
    inserted and what the user takes out stays, proposed deleted, a run of
    typing and a replacement each one proposal under the user's name; the
    user's own proposed insertion goes when taken out, as if never written,
    and a paragraph split or joined proposes its end. Formatting and structure
    apply at once. An action reviewed as "propose" (the registry's `review`)
    carries out its operations under the user who runs it, dated with the
    run: what `text`, `insert`, `table` and `delete` write and take out comes
    as proposals, each operation one, a replacement after the text it
    replaces; the user's own proposed insertions taken out go as in the
    Suggesting mode; its formatting and structure apply at once. A4's model
    writes through it.
  - *AI.* The backend calls the Claude API through its Python SDK (MIT). The
    target goes with its element addresses (D8); the tools are the operations,
    limited per action (summarise may add a block, never delete one); a model
    never computes a number, it writes formulas and IronCalc computes. The
    model is chosen per action, a small one for simple work. AI is off by
    default, yet an action that needs it stays enabled: running it first asks
    in the app's dialog, naming what leaves the server and where it goes, with
    use AI this once, always in this document (for those who may edit it,
    withdrawn from the document's menu) or cancel; an action with a part in
    code also offers to run without AI, leaving the unclear cases listed. Code
    actions send nothing out.
    *Decided 2026-10-21* (Ivo: "slažem se"): the administrator turns AI on
    for the installation on its own page beside Users, with the
    installation's Anthropic API key, checked with one call when saved,
    kept in Postgres encrypted with the installation's secret and never sent
    back to a browser (its last four characters show); a key the secret no
    longer opens asks to be entered again. Each action names its model once,
    in the registry: Opus 5.5 to rewrite, translate and extract into a table,
    Sonnet 5.5 to summarise and to describe a version's changes, Haiku 5.5
    to turn a search into filters. A model's run goes on in the
    background: the request returns the run at once, the run bar shows it
    working and offers Stop, and what it wrote stays as proposals for Undo
    action to take back together; a run the server's restart cut off is
    marked interrupted. A translation into a new tab is written as it is,
    not as proposals, as it replaces nothing. Tests drive the model with
    recorded tool calls; none calls the API.
    *Built 2026-10-21, step one:* the installation's setting and a
    document's consent (`apps/ai`), a model's run in the background with
    Stop, Undo and a restart's interruption, and Summarise end to end: the
    model reads the blocks the selection reaches, or the whole tab, as lines
    after their ids, and its one tool, insert, puts the summary after them,
    or after the tab's title, as proposals. Opus and Sonnet calls carry
    Anthropic's server-side fallback, so a request its safeguards decline is
    answered by the model they fall back to; Haiku has none.
    *Built 2026-10-21, step two:* Rewrite, one action whose one parameter
    picks the way (more formal, simpler, shorter, spelling and grammar
    corrected), each way a command of its submenu. Opus writes each chosen
    block's whole new text through the operation rewrite, which changes only
    the words that differ, as one proposal per block, a new word taking the
    formatting of what it replaces; the model may write only the blocks
    chosen, and a block with proposals waits until they are settled.
    *Built 2026-10-21, step three:* Extract into a table: Opus reads what a
    summary reads and makes one table where a summary goes, as proposed
    rows, its shape chosen from the text (a datum and its value a row for one
    thing such as a contract, a row each and a column per property for
    several things of one kind), its numbers, amounts and dates typed as the
    document's language types them and computed amounts as formulas, so
    IronCalc computes them.
    *Built 2026-10-22, step four:* Translate into a new tab, one action whose
    one parameter is the language (the document languages, each named in the
    interface's language, `en` as American English), each a command of its
    submenu. The run copies the tab as the last one beside it, named after it
    and the language ("Ugovor – Deutsch"), with its own tables renamed apart
    and its own header and footer, and Opus writes in the copy as it is: each
    block's and footnote's whole text through the operation replace, its
    formatted parts and its notes and fields tagged in place, so the
    translation keeps them; each cell of text through cells; each chart's
    title and image's description through set. Numbers, formulas and names
    stay. A tab with proposals waits until they are settled; Undo closes the
    copy, kept in a version first, and a run that fails closes it without a
    trace.
    *Built 2026-10-22, step five:* Compare with a version…, an action whose
    one parameter is the version, chosen in a dialog that lists the
    document's versions, the latest first. Code finds what changed in the
    tab since then: each block, footnote and table row added, removed, moved
    or changed, a changed text word by word. Sonnet reads only that and
    writes, as a proposal where a summary of the whole tab goes, a short
    paragraph naming the version and a list of the changes that matter, from
    what to what, those of spacing or punctuation alone left out. A tab the
    version holds as it stands is refused before anything is sent.
    *Built 2026-10-22, step six:* an action's plan comes before its consent,
    so a target with nothing to send is refused without asking. A4's
    predefined actions are built. Tidy import, an action with Haiku for its
    unclear lines, was built here too; since 2026-10-25 the import does it
    in code (F2, the Word import).
  - *Free prompt.* "Other…" is a model with every operation as a tool, always
    as proposals, under the same consent. Its runs are where new actions come
    from: what repeats becomes a predefined action, and that, where it can,
    code.
    *Built 2026-10-22, A5 step one:* "Other…" opens a dialog for the request,
    which applies to the blocks selected or, with none, to the tab. Opus, at
    high effort, reads the whole tab: each block with its type, attributes and
    text tagged as Translate reads it, what each tag holds and the proposals
    it carries, each table's cells with their formulas, values and looks, and
    the document's styles. Every operation of the tab and of the document's
    styles is its tool. "Always as proposals" means what A3 settled: text it
    writes is proposed, formatting, structure and tables apply at once, and
    Undo takes the whole run back. A range can be given by the words it holds,
    at their first occurrence or the one counted, since a model cannot count
    characters. A run's operations give no proposal, as a mark or an
    attribute: the editor's carry those of the text they move, but only a
    proposer or an importer writes one, so a model cannot write a proposal
    under someone else's name. The mark operation's schema checks each mark's
    attributes as `schema.json` defines them, and tells the model of them in
    the field's description, since a tool's schema takes no conditions at its
    top. Where it made an assumption, left part of the request undone, or was
    asked a question, its one or two sentences are kept with the run and shown
    in the run bar; Undo is shown only where a run changed something.
    *Built 2026-10-22, A5 step two:* each model's run records, answer by
    answer, the model that gave it, the tokens read anew, written, read from
    the cache and written to it, and their cost in dollars at the price list
    in `apps/ai/model.py`; where a fallback took over, each attempt is priced
    at its own model's rate (`usage.iterations`). A model without a price is
    logged as an error and leaves the run's cost unknown. The run also keeps
    whose consent let the text out: the user's own for this once, or whoever
    gave it for the document. The administrator's `/ai` page shows the last
    twelve months by month and action (runs, tokens, dollars), and the free
    requests grouped by their text with how often and when last, without the
    user or the document; those that repeat are the next predefined actions.
    *Built 2026-10-22, A5 step three:* the first action over a folder,
    "Extract data into a table…", on the documents and PDF files selected in a
    folder and those directly in the folders among them. Its dialog takes the
    new document's name and, optionally, the table's columns; without them
    Sonnet chooses at most twelve from the first document and the rest follow
    them. Each document is an item of the run in Postgres, which a loop in the
    backend goes through one at a time, carrying on after a restart; Sonnet
    reads each as Summarise does, a PDF page by page, and gives its row through
    one tool. A document it cannot read (gone, no longer readable to the user,
    empty, too long) or one the model refuses is skipped with why, and a
    failure of the model itself skips the rest. At the end, or once stopped,
    the rows found become one table, its first column each source's title
    linked to it, in a new document beside the selection, or at the top of the
    user's documents where the selection spans folders. The folder page shows
    the run's progress, what it skipped and why, Open, and Undo, which moves
    the document to the trash; a run that found no row says why and puts the
    empty document in the trash. Its consent is this once, given in the dialog.
  - *Order.* After the Pages view (f4-1): A1 operations (the schema in one
    place, the operations, undo per run, the importer on the same layer); A2
    the action registry and runs with the first code actions; A3 proposals,
    with Word's tracked changes both ways. Then slides, pptx and F5 through the
    filter, with A4 (the model, consent, the first AI actions) and A5 (free prompt, actions over a folder) beside them.
- **D15: the suite — closed 2026-10-20** (Ivo: "kao aplikaciju koju bi svaki
  korisnik mogao lokalno podignuti", "ne dižemo naše email adrese nego da se
  postojeći mailovi koriste", then "ok"). PONISTRA grows into the rest of what a
  firm needs to work without Microsoft 365: a mail client, calendar and contacts,
  chat and meetings, on the same core (one directory, one Postgres, one search,
  the same actions), as Django apps in this backend and frontend, not separate
  repositories. Engines come in only where a protocol has more rules than we
  should rediscover (D4's reason): LiveKit for meeting media. Everything else is
  ours.
  - *A product each organisation installs.* One installation is one
    organisation. Versioned images in a registry, one install command,
    first-run setup (administrator, domain, TLS), migrations on update, backup
    and restore with an off-site target, a health page. The installation
    watches itself: a problem that holds (a silent service, late snapshots or
    archiving, a full disk, a stalled queue) reaches the administrators as a
    notice, and one journal keeps sign-ins, accounts and settings for a year
    (U6, U7); no metrics export, as an installation has nothing to scrape it. Our production (D1) is
    the first installation of a released version, by the same path. No image
    comes from Microsoft's registry: the printer's Playwright base goes.
  - *Identity.* The directory is ours, in Postgres: people, groups, passkeys,
    and app passwords for phones' CalDAV and CardDAV. Keycloak would be a
    second directory; Zitadel is AGPL since v3.
  - *Mail is a client, not a server.* Users connect the mailboxes they already
    have at any provider: IMAP with a password, ActiveSync where only phones
    are let in (HCL Traveler, Exchange on premises), Google and Microsoft
    through OAuth. Google Workspace has required OAuth for IMAP and SMTP since
    2025-03-14 unless its administrator allows app passwords; Exchange Online
    IMAP has taken only OAuth since 2022, and its password SMTP is off by
    default from December 2026, with final removal to be announced for the
    second half of 2027. Each installation registers its own OAuth client at
    each, which its administrator enters in PONISTRA. Delivery, spam and
    viruses stay with the provider: no MX, port 25 or IP reputation is ours.
    The provider's mailbox is the source; our copy in Postgres is derived, for
    the one search, actions and speed. Sync runs in the backend (IMAP IDLE), so
    rules and triage work with the browser closed. Credentials are encrypted
    with the installation's key; HTML is sanitised, remote images stay blocked
    until allowed and then come through PONISTRA, fetched once and kept, so
    the sender learns neither the reader's address nor when they look again
    (no address inside a private network is called), attachments open only through our converters. A shared
    mailbox is connected once and shared through grants. Moving mail from one
    account to another is how a firm leaves Microsoft 365.
  - *Calendar and contacts are ours,* in Postgres, served to phones over CalDAV
    and CardDAV; most mail providers have no calendar, and invitations go both
    ways as iMIP through the user's mail account, so Outlook and Gmail
    invitations work. Free/busy, rooms and resources. A task is an element with
    an owner and a due date, made from a mail, a meeting, a message or a
    document, in one list rather than an app of its own. Mail comes before the
    calendar because invitations need a connected account.
  - *Chat is ours,* on the realtime layer the documents use: channels, threads,
    mentions, files from the tree, presence. Phones get Web Push from the
    installed web app, with no vendor relay. Matrix (Synapse, Element) and
    Mattermost are AGPL; Zulip is a separate product whose phone notifications
    for more than 10 users go through its paid service.
  - *Meetings:* LiveKit (Apache-2.0) carries the media, its own TURN the relay
    where a network needs one (S0 proved it enough, so coturn is out); the
    interface is ours. Guests join by link; meetings can be recorded; a
    transcript becomes a minutes document with tasks, through the speech to
    text of D28 and, like every AI step, only once turned on. Media needs
    one reachable UDP port; an installation without one runs a small edge
    (TURN and media) on any VPS, connected from the installation.
  - *Nothing needs to leave the organisation's network.* No CDN, no telemetry,
    updates from a file, and Web Push can be turned off (notifications then
    come only while the app is open). AI is the one part that goes out: the
    Claude API with the installation's own key, off until the administrator
    turns it on (D14). Without it, actions run as code and the AI ones show as
    unavailable. No local model (Ivo, 2026-10-20): a small model on a small
    firm's server gives worse results without an error, prompts and tool use
    would be tested twice, and the server would need a GPU.
  - *Licence:* PolyForm Noncommercial 1.0.0 (`LICENSE.md`, D29), as DIDA,
    BABA and OPUS. The About dialog in the account menu shows the author, the
    licence, the source and the version. Outside contributions are not
    accepted, so Ivo stays the sole holder. Before the repository goes
    public, its history names Ivo as the author of every commit.
  - Our own hosts' off-site backup (restic to Ivo's Microsoft 365 OneDrive)
    needs a new target before the subscription ends.
  - *S0, measured 2026-10-22* on LXC 210 (amd64, dev builds), memory as each
    container's cgroup counts it, page cache included. At rest the documents
    part takes about 0.9 GB: backend 180–250 MB, Postgres 130–180, printer
    120–320, converter and OCR 10–130 each, nginx 10. The heaviest jobs peak at
    1.65 GB in the printer (Tracking, 3.5 MB of PDF in 76 s), 0.78 GB in OCR (a
    5.4 MB scan, 26 s), 0.64 GB in the backend (importing Tracking, 22 s) and
    0.27 GB in the converter. LiveKit 1.13.10 holds 80–110 MB at rest, 140 MB
    for six people each sending video and sound (0.14 of a core; 3.6 Mbit/s to
    each, 21 Mbit/s out of the server) and 250 MB for twelve; coturn 17 MB. The
    images take about 3 GB, 1.8 GB of it the printer's Playwright base that S1
    replaces. All of it at once stays under 4 GB, so the smallest host we name
    is 4 cores and 8 GB with 40 GB of disk before content; the meeting's
    bandwidth, not its memory, is what limits a firm's own line.
  - *S0, a meeting from outside, 2026-10-22*, on the house line: a public IPv4
    on the operator's router (no CGNAT), UDP 7882 and TCP 7881 forwarded through
    it and OpenWrt to LiveKit, signalling through the Cloudflare tunnel as a path
    of the app (`/livekit`), a stock browser client. A phone on mobile data (the
    operator's own CGNAT) joined over UDP to the forwarded port and kept its
    session when it left Wi-Fi; a Windows laptop and four simulated people made
    six, with the server at 126–137 MB and 0.11–0.12 of a core, no loss between
    the simulated ones. The phone's path held 0.5–0.7 Mbit/s, so LiveKit sent it
    the lower simulcast layers rather than letting it freeze. With UDP moved to
    a port nobody forwarded, the laptop fell back to TCP 7881 and the phone still
    came in over UDP: both routers keep the source port, so LiveKit's own checks
    punched the hole. That is luck of the routers, not something an install can
    count on; the install asks for the one UDP port and the TCP one, and LiveKit
    checks at start (STUN from that port) that its public address answers.
    LiveKit's own TURN on UDP 3478, one more forwarded port, carried a phone on
    mobile data whose browser was allowed only relayed candidates: it joined,
    sent sound and video and received the laptop's. The relay's own ports
    (30000–30100) needed no forwarding, because the relay and the SFU reach each
    other through the router. The same relay offered only as TLS on TCP 443 (a
    name pointing straight at the public address, not through Cloudflare, and a
    Let's Encrypt certificate taken over that port by TLS-ALPN, so port 80
    stays shut) carried the phone too: two TLS connections from the operator's
    address, one each way, and nothing else open to it. That covers a network
    that lets out only HTTPS. Within minutes of the certificate being issued,
    scanners from elsewhere were connecting to 443, the name having been
    published in the certificate logs; whatever an install opens is found at
    once, so it opens only what LiveKit needs.
  - *S0, arm64*: IronCalc, the one engine of our own in Rust, cross-compiles for
    aarch64 on an amd64 host in five and a half minutes (maturin with zig), where
    building it under emulation would take hours. Under QEMU on the dev host
    (2026-10-23) the other five prod images build for arm64 in twelve minutes,
    and the whole stack starts, migrates and answers. Tracking imports with the
    same peak as on amd64 (648 MB), the converter turns a .doc and an .xls,
    and OCR reads a five-page scan; emulation runs them 10–50 times slower, so
    its times size nothing. Chromium for arm64 prints in a single process, but
    under QEMU's user mode it cannot start a process of its own, so the
    printer waits for real arm64 hardware. LiveKit, coturn, Postgres, nginx
    and node ship arm64 images.
  - *S0, long requests*: the prod frontend's nginx gives a request 60 s and
    Cloudflare gives it 100 s, while saving Tracking as PDF takes 76 s and
    importing it 22 s on amd64, each in one request. A bigger document or a
    slower host fails with a 504 while the backend goes on working. A longer
    timeout in nginx would not help, Cloudflare's stays. So everything whose
    time grows with the document is a job (2026-10-23, Ivo: "da"): saving as
    Word, Excel, PowerPoint, PONISTRA or PDF, importing a file as a document or
    into one, copying a document, composing and redacting PDF pages. The
    browser hands it over (`POST /api/jobs`, checked there as the request was),
    asks every second where it stands and downloads the file it made; no
    request waits on the work. The backend goes through the queue in Postgres
    `PONISTRA_JOBS_AT_ONCE` at a time (2 by default, 1 on a host of 4 GB),
    checks the user's rights again when a job's turn comes, and gives the
    printer a session of the user's own; a job a restart cut off runs again
    once, an ended one and its file are kept an hour. A file with its notes
    written in stays one request: it is how the viewer opens a PDF, and writing
    the notes takes seconds.
  - *S0, mail: Gmail, 2026-10-23*, Ivo's personal Gmail through an app password
    (2-step verification on), from LXC 210 on the house line. IMAP and SMTP
    both log in; Gmail offers IDLE, CONDSTORE, MOVE, UIDPLUS, ESEARCH,
    SPECIAL-USE, COMPRESS=DEFLATE and X-GM-EXT-1, not QRESYNC, so a resync is
    CONDSTORE plus Gmail's own message ids. All Mail, 3,188 messages and
    379 MB: every message's headers, flags and labels in 3.8 s, every body in
    68 s (5.6 MB/s), a CONDSTORE resync with nothing changed in 0.04 s,
    UIDVALIDITY unchanged. Google publishes 2,500 MB a day of IMAP download
    for Workspace, so a larger mailbox syncs its headers first and its bodies
    over days. A message sent to oneself shows to `STATUS` 7 s after SMTP takes
    it, but IDLE reports it only after 27–28 s, the same on a bare TLS socket.
    One from outside (Ivo's work address) reached Gmail a second after it was
    sent, showed to `STATUS` 10 s after Gmail stamped it and to IDLE 38 s
    after: the delay is Gmail's, so IDLE alone means over half a minute there.
  - *S0, mail: a plain host, 2026-10-23*. Ivo has no mailbox at a plain
    provider, so Dovecot 2.4.5 stands in for one, as most hostings run it
    (cPanel, Plesk), in a container with no network, filled with 3,000
    messages through APPEND. It offers IMAP4rev2, CONDSTORE, QRESYNC, NOTIFY,
    MOVE, PREVIEW and COMPRESS=DEFLATE. After another session marked 25
    messages and expunged 10, `SELECT … (QRESYNC (uidvalidity modseq))` returned
    `VANISHED (EARLIER) 26:35` and exactly the 25 changed messages in 0.01 s;
    IDLE reported a new message 0.5 s after it was appended. Times on a local
    server are not measurements; the protocol is what this proves. Dovecot
    changed a new mailbox's UIDVALIDITY as it created it, so the client treats
    a changed UIDVALIDITY as a full resync, not as an error.
  - *S0, mail: Google OAuth, 2026-10-23*, a client of Ivo's own in a new Cloud
    project: the Gmail API on, the consent screen as External in Testing with
    Ivo as its test user, the restricted scope `https://mail.google.com/`, a
    Desktop client with PKCE and a loopback redirect. The user's part is one
    consent screen ("Google hasn't verified this app", then Continue); the
    code traded for tokens in 0.2 s, IMAP and SMTP took the access token
    through XOAUTH2, a refresh gave a new one in 0.1 s without rotating the
    refresh token, and IMAP took that too. The administrator's part is six
    screens of the console (project, API, consent screen, audience, scope,
    client), each with its own address (`/auth/overview`, `/auth/audience`,
    `/auth/scopes`, `/auth/clients` with `?project=`), so setup links straight
    to each and checks the pasted client id and secret. An installation uses a
    Web client with its own redirect address instead; an organisation on
    Google Workspace makes its consent screen Internal, which Google neither
    verifies nor limits. An External one stays in Testing (100 test users, a
    refresh token Google documents as lasting seven days) unless Google
    verifies it, which the restricted scope ties to a yearly security
    assessment, so a personal Gmail on an installation goes through an app
    password.
  - *S0, mail: Microsoft, left out 2026-10-23* (Ivo: "zaboravi microsoft
    kompletno"). Ivo's only account is a personal Outlook.com, which has taken
    IMAP only through OAuth since 2024-09-16; its client would need an Entra
    tenant, which a personal account gets only through an Azure account with a
    card, and there is no work account for an organisation's Microsoft 365.
    S0 proves nothing about Microsoft's mail.
  - *S1, decided 2026-10-23* (Ivo: "slažem se sa odlukama"). Released images
    go to GitHub's registry as `ghcr.io/bacinac/ponistra-<service>`, public
    since 2026-11-04 (Ivo: a new organisation runs the install command alone,
    without signing in to a registry) while the repository and its history stay
    private; the backend's image leaves the tests out, as their fixtures hold
    real names. Each release also comes as one file of the same images, for an
    installation that updates without a registry.
    Production is LXC 104 on mlaka (D1).
  - *S1, off-site, decided 2026-10-24* (Ivo: "idemo s r2", the design below
    accepted the same day). An installation's off-site copy is an S3 bucket
    its administrator names on *System health*: endpoint, bucket and key pair,
    checked before they are kept, the secret sealed with the installation's
    secret key. Ours is Cloudflare R2 in the EU jurisdiction, in place of the
    Hetzner Storage Box: 10 GB a month free and restores free of egress.
    - *Locks.* The backend's key can delete what it writes, so what keeps a
      server taken over from wiping the copy is the bucket's own lock rule,
      which that key cannot change: the whole bucket, at least 30 days.
      Proved on R2: restic straight on a locked bucket cannot remove its own
      lock files, and the ones left block `check`, `forget` and `prune`.
    - *Mirror.* So the copy is the local repository mirrored file by file.
      restic writes each file once and names it by its hash, so the mirror only
      adds, checks the hash against the name first, sends the snapshots last
      and leaves the lock files home. It runs after each snapshot, at start
      and on a new key.
    - *Generations.* A snapshot leans on packs as old as the repository, so
      every 28 days the mirror starts a generation, every file again under a
      prefix named by its first day. The newest generation is whole and still
      locked; the older ones are deleted, oldest objects first, as their locks
      run out, so the bucket holds about two copies. A generation holding
      another installation's repository stops the mirror.
    - *Canary.* A generation's first object is a canary the mirror tries to
      delete after each run: the refusal shows the lock holds, and System
      health says when it does not.
    - *Recovery kit.* Saving the bucket adds an emergency key to the
      repository and shows the kit once, to download or copy: endpoint,
      bucket, key pair and that key. A new kit replaces the emergency key; the
      copies already in the bucket open with the old one until they expire,
      so a kit in the wrong hands also needs a new access key. `ponistra
      recover <kit>` in an empty directory fetches the newest generation, takes
      `.env` out of its newest snapshot with the emergency key and restores
      the installation at that snapshot's version.
    - *Check and trial restore.* Once a day after the night's mirror, restic
      checks the generation in the bucket directly (`--no-lock`, nothing is
      written there) and reads a different 1/28 of its data each night, so a
      generation is read whole once in its life. Every 30 days, and the night
      after a failure, the newest snapshot is restored from the bucket into a
      database beside the one in use, which must name no file the snapshot
      lacks, and is dropped. System health shows both with their dates.
    - *Locks a killed restic leaves.* Each run begins with `restic unlock`,
      and the backend, converter, OCR and printer containers run under
      `init: true`, so a restic killed by a reload is reaped instead of
      staying a zombie whose lock looks alive.
  - *S1, company folders and access (D20), built 2026-10-24.*
    - *Company.* A company folder is a top-level folder the administrator
      makes on *Users*, with a role for each group and for everyone, at least
      one of them owning it; the administrator holds no grant of their own and
      deletes a folder only once it is empty. Its members work inside it as
      their role allows, but the folder itself keeps its name, place and
      grants; its owners may still set *no download* on it.
    - *No download.* A folder option its owners set, inherited by everything
      below, binding everyone below owner: the original, the annotated PDF, a
      file's download, an import's source and every export are refused, and
      so is a copy, a joined PDF or an action's result that would land outside
      the folder. A document moves only within it; a folder that carries the
      flag itself takes it along. The interface disables these, printing too,
      since a browser's print saves a PDF.
    - *Log.* Opening a document or file (once an hour per person), every
      download and every change of a grant are logged; a node's owners read
      the latest 200 entries of it and everything below.
    - *Sessions.* Each session row carries its user, browser, address, sign-in
      and last activity (marked at most every five minutes). A user ends their
      own on other devices, an administrator any of anyone's, and ending one
      also closes its live documents. Deactivation ends them all; a deactivated
      user's documents stay theirs and come back with the account.
    - *Passkeys.* The policy asks nobody, the administrators or everyone; a new
      installation asks everyone (D33). It holds at sign-in: a covered user who
      has a passkey cannot sign in with a password; one who has none signs in
      once, can do nothing but add one or sign out, and cannot remove their last.
  - *S1, the vault (D20), built 2026-10-25.*
    - *Keys.* A random vault key opens everything and is sealed several ways:
      by the vault password through Argon2id in the browser (hash-wasm, MIT;
      64 MiB, 3 passes, 4 lanes), by the recovery code (32 characters,
      Crockford base32, shown once), by each passkey whose PRF the browser
      gives, and by the company's recovery key when that is on. Each user has
      an X25519 pair whose private half the vault key seals; a collection's key
      is sealed to each member's public key, an item's key by its collection's,
      an attachment by its item's; AES-256-GCM throughout (WebCrypto). The
      server holds sealed bytes and the collections' names, nothing it can
      open, so it cannot grant access either.
    - *Unlocking.* The vault key lives only in the tab's memory and locks after
      5, 15 or 60 minutes without a key or a click (15 unless the browser keeps
      another choice). The password opens it, the code too (a new password is
      then set), and a passkey with PRF where the browser and the authenticator
      give one; passkeys are now made with PRF asked for, since security keys
      and Windows Hello give it only then. With both password and code lost a
      user starts again: their vault, their own items and every key they hold
      are given up.
    - *Recovery through the company.* Off unless an administrator turns it on;
      the recovery pair is made in their browser, its private half sealed to
      them, and they confirm the other administrators who have a vault. While
      it is on every vault is sealed to it at its next unlock, and the user
      sees that. *Recover vault* on Users prepares a one-time code the
      administrator hands over in person; with it the user opens the vault and
      sets a new password, and sees who recovered it and when. Whoever can
      recover a vault can read it, which is why it is a policy for everyone or
      no one.
    - *Three roots.* My vault, Shared and Company. A user makes shared
      collections and gives users, groups or everyone read, edit or own; the
      administrator lays out company collections for groups on Users without
      reading them, and their first owner who opens one sets its key. Someone
      new waits until an owner, who holds the key, confirms them; whom an
      owner's own addition reaches is confirmed at once.
    - *Items.* A login (addresses, user name, password with its last 10,
      one-time code by TOTP, notes) or a note, with encrypted attachments and a
      password generator. In a shared or company collection, opening it and
      seeing a password or a one-time code (each once an hour per person), a
      member confirmed and a grant changed are logged for its owners. Deleted items go
      to the trash, which owners empty. Logins come in from Bitwarden (JSON or
      CSV), Chrome, Edge, Firefox, KeePass and KeePassXC, and go out as
      Bitwarden's unencrypted JSON; a company collection only by its owners,
      and its export is logged. Cards and identities come with the browser
      extension that fills them in.
    - *Folders, 2026-10-25.* A collection's items sit in folders within folders,
      their names sealed by the collection's key, so a shared collection's
      members see the same ones; deleting a folder leaves its items at the
      collection's top. A long press chooses several items to move or put in
      the trash, as in mail. Bitwarden's folders and KeePassXC's groups come in
      as folders and go out as Bitwarden's. *Sort into folders…* lets out, this
      once and after the user agrees, only each unfiled item's name and the
      host of its first address to Claude Sonnet, with the names of the
      folders the collection has; the user renames, joins and moves what it
      proposes before the browser seals and files it. Of that the server keeps
      only the run with the tokens it took.
  - *S1, the printer on Debian's Chromium, 2026-10-23.* The printer runs
    Debian trixie's `chromium-headless-shell` (156) on `node:26-slim` instead of
    the Playwright image: Debian's security updates, an arm64 build, and no
    Microsoft registry or CDN. The image is 586 MB instead of 1.79 GB. Debian's
    Liberation and Noto fonts (core, CJK, colour emoji; OFL) are what the print
    page falls back on, after the documents' own fonts. On Tracking it lays out
    the same 997 pages at the same 1.65 GB peak, but saving it as PDF takes
    104–106 s instead of 84 and counting its pages 9.1–9.4 s instead of 6.7.
    Fonts are not the cause: without the Noto sets it took 111 s. The cost is
    Debian's build of Chromium against Playwright's, and saving as PDF is a
    long job in the queue (S0, long requests), so no request waits on it.
  - *S1, an installation, 2026-10-23.* `compose.yaml` is what an organisation
    runs: the released images at one version, `.env` and the data under
    `volumes/`; the dev host lays `compose.override.yaml` over it. Caddy (Apache
    2.0) serves the built app and fetches the domain's certificate, or serves
    plain HTTP behind a proxy or tunnel that ends TLS, and hands the backend the
    reader's address alone. `scripts/release.sh` releases origin's main as
    `MAJOR.MINOR.<commit count>`, first 0.1.94. The release image
    `ghcr.io/bacinac/ponistra` carries `compose.yaml` and the `ponistra`
    command: `docker run --rm ghcr.io/bacinac/ponistra > ponistra && sh ponistra
    install` asks for the domain and where TLS ends, writes `.env` with fresh
    secrets and starts the stack; `ponistra update` takes the newest release, a
    version or a release file. Install prints a one-time code of 16 characters
    (about 79 bits). While the installation has no user, the browser opens on
    *First start* instead of signing in, and that code, a name, an email and a
    password make the first administrator, who is signed in. The table is locked
    while it is checked, so two people setting up at once get one administrator.
  - *S1, snapshots and updates, 2026-10-23* (Ivo: "fokusirat ćemo se sad na
    lokalno izdanje": an installation on the organisation's own hardware first,
    the off-site copy and production after). One restic (BSD-2) snapshot holds the
    database (an uncompressed custom dump, so unchanged parts deduplicate), the
    files and `.env`, whose secret key opens what is sealed with it. It goes into
    `volumes/backup`, encrypted with `RESTIC_PASSWORD`, which install generates;
    away from that disk, the off-site copy's recovery kit opens them. Snapshots are kept for 7 days, 4
    weeks and 12 months. The backend takes one each night at 03:00, and at
    start when the machine was off that night. A snapshot holds back file
    collection, so each file the database names is still there, and runs one at
    a time. `ponistra backup`, `backups` and `restore [<snapshot>]` work on
    them. A restore puts the files back, restores the database beside the one in
    use and swaps it in only once it is whole, and it brings back the version
    that took the snapshot. `ponistra update` stops the frontend, snapshots,
    starts the new version, and if it does not answer it writes its log to
    `update-<version>.log` and puts the old version back with that snapshot's
    database. Each release runs its own update, since only it knows what it needs
    that the one before did not. Going back is a restore; an update never goes to
    an older version. 0.1.94 and 0.1.95 take no snapshots and are installed anew.
    *System health* (administrators) shows the version, whether the services
    answer, the newest and next snapshot (in red when a night's is missing), the
    database, the files and the free disk, and what waits in the queues.
  - *S8, a restore to any moment, 2026-11-10* (analysis finding S8: an installation without its
    host's snapshots lost up to a day). A snapshot holds a base backup of the cluster
    (`pg_basebackup`, file by file and uncompressed) in place of the dump. Postgres archives every
    WAL segment, gzipped, into `volumes/wal` once full or after 5 minutes with anything written,
    and every 15 minutes the backend takes that spool and the files into a snapshot of their own
    (host `ponistra-wal`), which the mirror carries off-site like any other: off-site the
    installation loses at most about 25 minutes. The collector moves a file nothing names into
    `dead/<date>/` and deletes it after 7 days (`store.KEPT`, the restore window), so a database
    restored to an earlier moment finds its files. `ponistra restore` takes a snapshot as it was,
    a moment of the last 7 days (`YYYY-MM-DD HH:MM`) or, by default, the newest moment the WAL
    reaches: the backend builds the cluster in `volumes/restoring` and replays the WAL in a
    Postgres of its own (the server is in its image), puts back the files that database names,
    and the command swaps it for Postgres's data, the old one kept beside until the new one runs;
    the version comes from the restored database itself (`backups.Migrated`, written after each
    migrate). A snapshot with a dump, taken before S8, is restored by the release that took it.
    The trial restore replays the bucket's newest snapshot with all its WAL the same way.
  - *S1, passkeys, 2026-10-23.* A passkey (WebAuthn through py_webauthn, BSD-3)
    is made from the account menu, one per device, and signs in from the sign-in
    page without an email or password: the device keeps it and asks for the
    fingerprint, face or PIN, the server keeps only its public key. It belongs to
    the site's own address, the one the CSRF check has already found in the
    request. A passkey removed in PONISTRA is reported unknown at the next sign-in,
    and the browser has the device forget it; a deactivated account's stays on the
    device. App passwords move to S4: CalDAV and CardDAV are all that would use
    them.
  - *S3, Microsoft, 2026-10-23* (Ivo: "bez Microsofta dok nema tenanta"). S3
    connects IMAP with a password and Google through OAuth. The account knows
    its provider, so Microsoft comes in as one more once a tenant exists to try
    it against (Ivo's or the first customer's); nothing is written that cannot
    be run against the real service. S5's Graph import waits the same way.
    Reversed on 2026-10-24 (*S3-4* below): Ivo's Outlook.com is that account.
  - *S3, accounts and sync, 2026-10-23.* An account is connected with its
    address and password. PONISTRA guesses its servers (its own table for Gmail,
    else the autoconfig the provider publishes, else `imap.` and `smtp.` of the
    domain), signs in to both and keeps the account only once both let it in,
    the password sealed with the installation's key as the AI key is
    (`apps/core/sealed.py`). A server without TLS is refused unless the
    installation names it (`PONISTRA_MAIL_PLAIN_HOSTS`, the dev and check
    stacks' mox), and the form disables it for any other. Where the provider
    takes only an app password for mail, as Gmail does for an account not
    signed in through Google (S3-4), the form asks for one and links to where
    it is made. While the backend runs, a loop of its lifespan follows each
    account on one connection in a thread of its own: INBOX in IDLE, so new
    mail is there at once; every folder caught up each five minutes (new
    messages by UID, changed flags through CONDSTORE, expunged ones by their
    count); and the text of each message, newest first, up to 256 KB. Postgres
    keeps the envelope, text, preview and where each part is once per message
    of the account, and each folder's copy of it with its UID and flags:
    Gmail's labels are folders, so one message sits in INBOX, All Mail and
    Important alike, and is known as one by Gmail's own id (elsewhere by its
    Message-ID hashed with its size, so that a message reusing another's id
    does not stand in for it). A message goes once a whole pass finds no folder
    holding it. The message itself stays with the provider and is fetched by
    its parts when it is opened (S3-2). A refused password stops the account
    until the user gives it again; a lost connection is tried again after a
    minute, doubling up to half an hour. The Mail module's panel holds the
    accounts and their folders in place of the document tree, the rail stays at
    the foot of a phone, and a folder lists fifty messages at a time.
  - *S3, reading, 2026-10-23.* A message opens beside its folder's list (alone
    on a phone, with a way back); its parts are fetched from the provider on one
    connection per account that the backend keeps while the user reads and
    closes after two idle minutes, since signing in takes longer than the read
    (1.2 s the first open, 0.2–0.5 s after). Every view that waits on a mail
    server is a coroutine: Django runs synchronous views on one shared thread,
    and one slow server would hold it for every user. The HTML is cleaned by
    nh3 (nothing that runs, links only out or to mail and phone, images only
    the message's own parts or inline data) and shown in a sandboxed frame
    whose policy lets nothing else load; it stays on white paper in the dark
    theme, as mail is written for it. Images from elsewhere wait until the
    reader lets them in for that message, since they tell the sender it was
    read. Opening a message marks it read, and read, unread and flagged are
    written to the provider (Gmail's for every label of the message). An
    attachment downloads, or becomes a document in the tree as an upload does.
  - *S3, ActiveSync, 2026-10-23.* An account is IMAP and SMTP or ActiveSync
    (MS-ASCMD 14.1), for the firms that let only phones out: a client company's HCL
    Domino closes IMAP and SMTP and answers ActiveSync on its Traveler. The
    client is ours over the standard library (WBXML, one kept HTTPS connection),
    no dependency. The account is a device the server's administrator sees,
    blocks or wipes: it takes the server's policy when asked (HTTP 449 or a
    provisioning status), and a remote wipe is acknowledged and its mail
    deleted here; it is then not followed until the user saves it again. Folders
    come from FolderSync with their paths built from their parents (only the
    mail ones; Traveler lists only those the user syncs to devices), messages
    from Sync with their envelope, flags and text, then Ping keeps each folder
    current. Traveler ends a device's open request when the device sends
    another (HTTP 409), so an account's requests take turns and only the Ping is
    left open, to be ended by a read and sent again. A message is fetched whole as MIME when it is opened and read into
    the same parts IMAP describes, by the same numbers, so reading, files and
    images are one path for both. Server guessing takes IMAP only where it
    signs a valid certificate (a company's autoconfig may point to its web
    host's mail) and otherwise looks for ActiveSync under the usual names.
    *Open, Ivo's:* Microsoft says patents may cover ActiveSync and licenses it
    on request; it is used for our own mail, and is decided before an
    installation for another firm offers it.
    - *Domino names, 2026-10-24* (Ivo: "da"). Traveler writes people of the
      organisation as Domino does (`Given Family/Organisation`), which no
      reply reaches. It answers no ResolveRecipients (status 5) but does answer
      Search in the directory (GAL), so each name is looked up there by its
      common name as mail is taken, the answer kept in Postgres per server
      (a name the directory does not know is asked again a day later), and
      mail taken earlier is rewritten once a name is found. A name the
      directory lists for several people or none stays as Traveler wrote it:
      a reply shows it, the compose window asks for the address, and sending
      refuses it until the user writes one, never dropping that recipient.
    - *Copies without a Message-ID, 2026-10-24* (Ivo: "da"). Traveler gives
      its own item id (`4:8870020`, the folder first) for a Message-ID, and the
      sent copy and the delivered one differ in it, in `X-IBM-UNID` and by a
      second in their dates, the delivered one sometimes earlier. Where either
      side lacks a real Message-ID, two copies are the same message by what it
      is made of: sender, recipients, subject, text and files, within two
      minutes of each other. Two items of one provider folder are never one
      message, however alike (a daily automated mail). This makes the user's
      Sent copy and the Inbox copy of a mail to themselves one message, and
      PONISTRA's own sent record one with the server's; a message deleted for
      good stays deleted in every copy.
  - *S3, sending and the combined inbox, 2026-10-24* (Ivo: "idemo"). Sync
    keeps each message's References beside its Message-ID (ActiveSync tells
    them when the message is opened, until its MIME comes with Sync), and a
    reply carries In-Reply-To and References so other clients thread it. With
    two accounts or more, *Sva pristigla pošta* lists every Inbox at once, each
    row in the colour of its account (seven colours from `theme.css`, chosen per
    account in its menu). A message delivered to two of the user's accounts
    (the same Message-ID and subject) is one row with both colours; it is read
    while every copy is and flagged while any is, and reading or flagging it
    does so on every server. Accounts that failed or are still syncing say so
    above the list. A new message goes from the account whose folder is open,
    in the combined inbox from the one marked default (the first connected,
    then the user's choice), a reply or forward from the account the message
    came to; the sender can be changed before sending. IMAP accounts send
    through their SMTP server and keep the copy in Sent with APPEND (Gmail
    keeps it itself), and Sent is caught up at once. ActiveSync sends with
    SendMail, or with SmartReply and SmartForward (ReplaceMime: the message
    goes whole as written) when the original is on the same account. The
    server keeps that copy itself. Checked on a client company's Traveler with a
    message to Ivo's own address: SendMail 0.4 s, in the Inbox 6 s later, and
    SmartReply accepted. Traveler does not send back that the original was
    answered, so PONISTRA marks it locally. Recipients the server refused while
    taking the others, and a Sent copy that could not be saved, are shown after
    sending. Found on the way: work run in a thread from an async view kept its
    database connection out of the pool of four until the pool timed out. Each
    such call now gives its connection back.
  - *S3, the mail is ours, decided 2026-10-24* (Ivo: "slažem se sa odlukama").
    PONISTRA keeps the mail; providers only carry it in and out, and PONISTRA is
    the only mail client Ivo uses. Each new message is taken whole once (IDLE
    and Ping stay only so it arrives at once) and never synced back. Reading,
    flags, moves and deletion change our copy only. PONISTRA writes to a
    provider for two things only:
    - it sends through it, and the provider keeps its Sent copy (for the
      company's archive);
    - it deletes old mail there, by the account's setting "keep at the
      provider: always / N days" (Gmail: moved to Trash). This stays off until
      S1-5 backups run and a restore has been tried, since our copy is then the
      only one.

    Postgres holds what is shown and searched: headers, text and the text of
    attachments (scanned PDFs through OCR), in one index with documents. The
    whole message and its attachments are files in the blob store (sha256), so
    a file sent many times is kept once, and the nightly backup adds new files
    instead of dumping a growing table.

    There is one folder tree per user, not per account: one Inbox, each message
    in its account's colour, and a provider's other folders imported under the
    account's name. A message that reached two accounts is one message.

    What was taken is not taken again: each folder keeps the mark it reached,
    and deleted messages are remembered by Message-ID and subject for a
    provider that resets a folder.

    On the phone, Ivo turns mail off in Verse and the Gmail app, and PONISTRA
    sends notifications there itself (web push).

    This removes flags and "answered" written back to providers, CONDSTORE and
    expunge tracking, and opening a message at the provider (ItemOperations,
    the IMAP read pool).

    Built 2026-10-24, with four choices Ivo approved ("slažem se"):
    - an attachment is cut out of the message's file only when encoding it
      again gives the same bytes; otherwise it stays inside, and the message
      is always given back exactly as it came;
    - a message held in several provider folders sits in one: Trash, then
      Junk, Inbox, Sent, a label, and Gmail's All Mail (our Archive). Gmail's
      Starred is the flag, and Important is not taken;
    - on the dev host the accounts stayed and their mail was taken again
      (Ivo's Gmail 3233 messages, his work mailbox 5436, 1.4 GB);
    - removing an account keeps its mail where it was, and its folders that
      hold none go.

    IMAP takes a new folder's mail from the newest down, 200 messages at a
    time, between new mail; ActiveSync takes each message as its MIME.

    Ivo, the same day ("slažem se"): marking a folder read stays in PONISTRA,
    as every flag does. Images from other servers are let in for a sender's
    domain as its From gives it (not the address, which is too narrow, nor
    the account, which would only switch the hold off), from the message and
    in a list the user keeps; the registrable domain is not derived, since the
    Public Suffix List is MPL. An account can be kept out of the shared
    folders: its mail is still taken and kept, but neither listed nor counted
    there, unless another account shown there brought it too; its name in the
    side column shows the shared folders with its mail alone.

    Ivo, the same day ("da", then "samo na long press"): a long press on a
    message starts choosing; boxes then show on the rows, a tap adds or takes
    away one, Shift a range and Space does it from the keyboard, and once
    none is chosen the list is as before. Over the list, in a row that stays
    on top, is what can be done to them: read, unread, flag, unflag, move to,
    archive, junk (in Junk: not junk), Trash (in Trash: delete for good,
    asked first). The box in that row chooses the loaded rows, and its menu
    every message of the folder, the read or the unread, as many as the list
    shows (of one account in its view). One request carries the choice as a filter, which
    the backend applies (`/api/mail/folders/<id>/chosen`), so a folder of
    thousands is not sent as ids; the reader's moves and its deletion go the
    same way. Archive and Junk are made the first time mail goes to them.

    Ivo, 2026-11-03 ("slažem se s preporukama i kreni"): a sender's mail can
    be blocked or always moved to a folder, by their address or by the whole
    domain they write from (its subdomains too), and nothing else: no
    conditions on subject, size or "and/or", which is Outlook's dialog; sorting
    by content, if it is ever wanted, is the AI's, as the vault's folders are.
    The reader's menu offers *Blokiraj pošiljatelja…* and *Uvijek premjesti u
    mapu…*, and the list's choice blocks the senders of the messages chosen.
    Blocked mail goes to Junk, not away: it stays found, and Junk is neither
    counted, nor waiting, nor notified. A rule takes the mail the user has at
    once and all that arrives after, through every account, at the one place
    mail comes in (`apps/mail/sorting.py`), before the message has a folder,
    so a blocked one never rings; the narrowest rule wins, an address over its
    domain. No rule takes mail out of Sent, Drafts, Trash or Junk, and nothing
    is written to the provider. *Nije neželjena pošta* takes away the block
    that sent the message to Junk. The rules are listed, and removed, in
    Postavke → Pošiljatelji, beside the domains whose images are decided,
    which move there from the mail page's menu.

    Ivo, the same day ("slažem se"): the band over a message whose images are
    held goes, its sentence with it; an icon on the reader's toolbar, there
    only while they are held, opens show them, always for the domain, and do
    not ask again. *Blokiraj pošiljatelja* stands on the toolbar beside
    Archive for mail that came through a list (it carries List-Unsubscribe,
    as RFC 2369 has a list give it), and stays in the menu for other mail.
    Unsubscribing through that header (RFC 8058) is a step of its own, as it
    writes to the sender.
  - *S3-4, Google and Microsoft through OAuth, 2026-10-24* (Ivo: "da, krenimo
    s tim", then "ok, nastavimo" to Google's app in production unverified).
    Ivo's Outlook.com (Microsoft 365 Personal) is the account Microsoft is
    tried against, and a free Azure account gives the Entra tenant its client
    needs. Both providers go one way: the authorization code with PKCE and the
    client secret, IMAP and SMTP through XOAUTH2, and the refresh token sealed
    as the account's secret, as a password is (`apps/mail/signin.py`).
    - Each installation registers its own client: a Web client at Google, and
      at Microsoft an Entra app for accounts in any directory and personal
      accounts. An administrator enters the client ID and secret on the page
      *Prijava u poštu* (`/providers`), which shows the redirect address the
      backend builds from the request (`/api/oauth/<provider>`), to be
      registered exactly so. Before the client is kept the provider is asked
      whether it knows it, by trading a code that cannot be good: a known
      client is told the code is wrong, an unknown one that the client is. The
      secret is sealed and only its last four characters are shown again. A
      Microsoft secret lasts at most 24 months, so its end date is kept and
      the page warns 30 days before.
    - Google: scope `https://mail.google.com/`, consent asked each time, since
      only then is a refresh token given; `imap.gmail.com:993` and
      `smtp.gmail.com:465`. An External app in Testing loses consent after
      seven days, so Ivo's is in production unverified: its users see "Google
      hasn't verified this app", and at most 100 may ever sign in through it.
      An organisation on Workspace makes it Internal, which has neither. The
      refresh token is not rotated; a password change ends it.
    - Microsoft: authority `/common`, scopes `IMAP.AccessAsUser.All`,
      `SMTP.Send` and `offline_access`; IMAP `outlook.office365.com:993`, SMTP
      `smtp.office365.com:587` for a work account and
      `smtp-mail.outlook.com:587` for a personal one, told apart by the ID
      token's tenant. Each refresh gives a new refresh token (90 days), kept at
      once; the old one is not ended.
    - An access token is renewed ten minutes before it ends, and the IMAP
      connection that signed in with it ends then and signs in again: Exchange
      Online drops a session whose token has run out. A refresh the provider
      refuses as `invalid_grant` (consent withdrawn, password changed) stops
      the account until the user signs in again, as a refused password does.
    - The account dialog offers *Poveži s Googleom* and *Poveži s Microsoftom*
      for the providers whose client the installation has. An account kept
      with a password at Gmail or Outlook switches to signing in through its
      provider in place and keeps its mail.
  - *S3, read within the organisation, decided 2026-10-24* (Ivo: "potvrđivanje
    pročitanog maila mi je prenapadno … ovaj 'whatsup' sistem unutar firme
    želim", then "da" to one setting for the organisation). PONISTRA neither
    asks for nor sends read receipts (MDN, RFC 8098):
    the compose window has no such box, and a `Disposition-Notification-To`
    header is ignored, as Gmail does. No mail it sends carries a tracking pixel.

    A click on a row of any list shows it: it opens the item, or, with a preview
    open beside the list (Boards, a folder's preview), shows it there and leaves
    the list. A double click opens it even then, and only once. A long press or
    Ctrl-click starts choosing, and only then do the bar and the checkboxes
    appear; a click then adds or removes, Shift takes the range (Ivo, 2026-11-09).
    The bar stays at the top of the list's scroller with no gap, and the row
    pressed stays where it was.

    The same choosing holds wherever a list's rows are acted on together (Ivo,
    2026-11-02, "isto ponašanje na long press kao u mailu"): the trash of
    documents and the vault's (restore, delete for good), the vault's items,
    a folder's rows, notes (move, trash) and contacts (write to them, delete).
    One part does it (`choice.tsx`, on `press.ts`), and each row action that
    has a list of its own is one request (`/api/trash/restore` and `/purge`,
    `/api/vault/trash/restore` and `/purge`, `/api/contacts/delete`). In a
    folder a click still picks the row the preview shows; the boxes and the
    bar lie over the column heads only while something is chosen, so no row
    moves under the pointer. Tasks keep their box for done, chat, alerts and
    the calendar have nothing to do to several at once.

    Between people of the same installation it shows what WhatsApp does, since
    both ends are ours and nothing leaves it. The sender's copy and each
    recipient's are the same message by their key (Message-ID and subject), or
    by what they are made of where a server gives no Message-ID (Traveler,
    under S3 ActiveSync), so
    the sender of a message, and no one else, sees which colleagues opened it
    and when; no receipt is sent and no third party learns anything. Only
    opening the message counts, not marking it read, one by one or all at once,
    and marking it unread takes nothing back. Chat (D15) follows the same rule
    when it comes.
    - A recipient is every colleague who holds the message, not only the
      addresses it names: a list such as `prodaja@` shows each colleague it
      reached, and Bcc those the sender chose. Holding it is its delivery,
      since sync takes mail at once. A recipient outside the installation has
      no status and is never shown as unread.
    - Sent shows a check when every colleague opened the message, otherwise
      how many did ("2/5"). The message says "Otvorili 2 od 5 kolega", and the
      list of who opened it when, who has not yet and how many are outside
      opens on a click; a message to the whole company stays one number.
    - In a shared mailbox (S3) it shows who of those sharing it opened it.
    - One setting of the administrator turns it on or off for the whole
      organisation, on by default; there is no switch per user. An employee's
      consent is seldom free (EDPB, guidelines 05/2020), so what it rests on is
      the organisation's legitimate interest and its notice to its people,
      which is the organisation's to decide. The setting says what it means:
      a sender from the organisation sees when you opened their message. It
      lives on the administrator's page Pošta, above the sign-in
      registrations, and turning it off erases every opening noted so far.
   - *S3, the sender and unsent messages, built 2026-11-02* (Ivo: "na koji
      način ćemo imati defaultni za neki kontakt", "zar ne bi za svaki mail u
      kojem je nešto kreirano a još nije poslano trebali snimiti kao draft").
      A new message goes from the account the user last wrote to its first
      recipient from, else the one that recipient last wrote to, else the
      default (`Correspondent.sent_from` and `reached`, kept as each message
      is counted); the composer follows the first recipient until the user
      picks the sender, and an account said into the microphone is chosen.
      What the user writes is kept as an unsent message (`Unsent`, the
      composer's fields) 1.5 s after each change and on closing, listed over
      the Drafts folder as *Nedovršene poruke*, opened in the composer as left
      and deleted when sent or discarded. It stays in Ponistra, as every
      action on the mail does: the servers' folders are not written, and
      the client company's Traveler speaks ActiveSync up to 14.1 while drafts arrived
      in 16.0.
  - *S3-6, shared mailboxes, built 2026-11-11* (Ivo: "Sandučić je svoj
    vlasnik"). A shared mailbox (info@, prodaja@) is a user of its own,
    `User.mailbox`, who never signs in and is not listed among the users; its
    accounts, folders, rules and mail are its own, so every mail view serves
    it unchanged. Colleagues reach it through grants (`mail.Grant`: a user,
    a group or everyone, as `read`, `edit` or `own`), and a request names the
    mailbox by `box`, which `sharing.boxed` checks against the role the view
    needs before acting as the mailbox (`request.user`), the colleague staying
    `request.person` for consent, openings and the log. Its owners connect
    its accounts, share and rename it; removing it takes its accounts and its
    mail. Each colleague's first opening is noted (`Opening`) and shown in
    the reader.
  - *S3-7, rules and triage as actions, built 2026-11-11.* What the user does
    to messages is a registry action on the target `messages` (D14):
    marking, moving, snoozing, awaiting, deleting, blocking a sender and
    sending a sender's mail to a folder, one plan each in `acting.py`, which
    the list, the reader, rules and the API share
    (`/api/mail/actions/<action>`). *Razvrstaj u mape* lets up to 50 chosen messages
    out to Claude once (sender, subject, the first 600 characters, and the
    user's own folders, archive and junk); it proposes a folder for each,
    and only the proposals the user ticks are moved, through `mail.move`.
    The editor's tab actions keep to the targets inside a tab (`TAB_TARGETS`);
    an outside agent gets the mail actions as tools of their own (`mail_move`
    and the rest, s3-12, 2026-11-12), done at once and kept as runs of its
    grant, but for `mail.delete`, as nothing an agent does deletes, and
    triage, as letting mail out to the installation's model is the user's
    consent to give.
  - *Search and agents over shared mailboxes (s3-10, s3-12, 2026-11-12).* The
    search box and its results find the mail of the shared mailboxes the user
    reads beside their own, each hit naming its mailbox and opening in it; an
    agent's mail tools act in the mailbox a message is in, reading on `read`
    and changing on `edit`.
  - *S3-8, moving mail between accounts, built 2026-11-11.* A job of the
    server (`mail-move`) puts every message one account brought into another
    account at its provider by IMAP APPEND, as it came, with its read, flag
    and answered marks and its date: the inbox, sent mail and archive into
    the other account's own (made where it has none), the account's folders
    into folders of the same names, made where missing, and in Ponistra
    under the other account; trash, junk and drafts stay. A moved message
    then belongs to the other account, which is how a move cut off goes on
    where it stopped; a message the other account already brought is
    skipped. Only into an account reached over IMAP; nothing is deleted from
    the one moved from.
  - *S4, contacts from every account, decided 2026-10-24* (Ivo: "ok"). As with
    mail, each connected account's contacts are taken one way and merged into
    one address book per user in Postgres:
    - Google through its CardDAV (proved 2026-10-25 on Ivo's Gmail: 215
      contacts, their photos and birthdays), signed in as the mail is: with the
      account's app password, or with its Google sign-in's token, whose scope
      gains `auth/carddav`. Google's *Other contacts* are not taken: the mail's
      own addresses stand for them (below);
    - Microsoft through Graph `Contacts.Read`, consented to at the same sign-in
      as the mail; Microsoft gives a token for one resource at a time, so the
      one refresh token is traded for IMAP's and for Graph's apart;
    - ActiveSync through Sync of its Contacts folder, with no new sign-in;
      Traveler's contacts and its directory are proved first, as S0 proved its
      mail;
    - another IMAP account only where its provider offers CardDAV.

    One person is one contact, merged by e-mail address, then by phone number.
    What each source gave is kept apart, as a folder's `Source` is for mail, so
    each field's origin is known.
    - A personal contact is taken once and is ours afterwards; a change in
      PONISTRA is not written back.
    - The organisation's directory (ActiveSync's GAL, later Entra or LDAP) stays
      its IT's: read and refreshed, never changed, so a colleague's new number
      arrives by itself.
    - The addresses of the mail itself (everyone written to or by, from the
      headers) are kept apart from contacts, like Google's *Other contacts*,
      and complete addresses while writing.

    The import comes with CardDAV for phones (an iPhone natively, Android
    through DAVx5, the phone's own app and no part of PONISTRA): a phone's
    dialer and WhatsApp read Google's contacts even with the Gmail app off, so
    until the phone reads ours, contacts taken would be a second truth. Google's
    contacts stop being a source then. The directory and the mail's addresses
    are only read, so they come earlier, with completing addresses in S3's
    compose window.
  - *S4, the colleagues the user meets, decided 2026-10-25* (Ivo: "kolege koje
    sretneš"). Proved first on Traveler and Outlook.com:
    - ActiveSync's directory cannot be listed, only searched by the start of a
      first or last name (two letters at least). Each correspondent the
      directory confirms as a colleague (the address it gives is theirs)
      becomes a contact whose source is the directory, refreshed by it at
      night; any other colleague is found by searching live, in the address
      book as while writing, and added with one click. The directory is never
      walked letter by letter: that is hundreds of requests a night to the
      organisation's server and every colleague on the phone.
    - Traveler's contacts are a folder of the account's hierarchy (type 9),
      taken by Sync as mail is; its calendar is another (type 8). A FolderSync
      from key 0 keeps the state of the folders already synced, so an account
      connected before S4-1 reads its folders once more and takes nothing
      again.
    - Microsoft's one refresh token gives Graph's token as well; contacts come
      through each folder's delta, new ones only, as new mail does.
    - Two items of one source are never one contact, as two items of one mail
      folder are never one message; a phone number merges only where one
      person holds it, so a switchboard shared by a firm joins nobody.
  - *S4, the calendar and the order, decided 2026-10-25* (Ivo: "slažem se s
    prijedlozima"). Built in this order:
    - `s3-complete`: recipients completed from the mail's own addresses and the
      organisation's directory, each chosen one a chip, the browser's own
      completion off on those fields;
    - S4-1: contacts from every account, with CardDAV for phones;
    - S4-2: the calendar, with CalDAV;
    - S4-3: invitations both ways, free/busy, rooms and resources, tasks
      (S4-3a invitations received and answered, then S4-3b the rest).

    A personal calendar (Outlook.com, Gmail) is taken once and is ours
    afterwards, as a personal contact is. The organisation's calendar (Domino
    through ActiveSync) stays its own: read and refreshed, never changed, and a
    reply to its invitation goes back through ActiveSync. Exchange's folders
    for Outlook on a computer (Notes, Outbox, Sync Issues) are not shown while
    nothing is in them.
  - *S4-1, the address book, built 2026-10-25.* Contacts are a module of the
    rail after Mail. A contact's address opens PONISTRA's own compose window
    (`/mail?to=`), its number the phone's dialer. A colleague's job title and
    company stay the directory's while it lists them, so they cannot be edited;
    the rest of what the user writes stands in front of the directory's. A
    phone reads one address book, "PONISTRA", at `/dav/` (found from
    `/.well-known/carddav`), signed in with the user's email and an app
    password made in the account menu, shown once and kept as its digest.
    Changes are numbered from one sequence and committed in that order under a
    lock per user, so a phone's sync token never passes a change committed late.
    Google is the foremost source (Ivo, 2026-10-25): its names are the ones the
    user wrote on the phone, diacritics and all, so where a Google card joins a
    contact another source named (Outlook's spelling without diacritics), Google's name
    (with them) replaces it; a name the user wrote in PONISTRA stays.
    Every phone number is kept written one way, internationally
    (`+385 91 234 5678`, by `phonenumbers` with Croatia as the home region),
    whoever gave it: a source, the user or a phone; one that cannot be read as
    a number, a short service number, stays as given. `091` still finds it.
    The book is in the order of the Croatian alphabet (ICU `hr`, as documents
    are): Andrija, Anđelka, Anita; Cvita, Čedo, Ćiro.
  - *S4-2, the calendar, built 2026-10-26.* Calendar is the module of the
    rail after Today: month, week, day and a list of the thirty days ahead
    (the list is where a phone opens, the month a wide screen, 2026-11-02),
    the panel holding a small month and the calendars with their colours
    (seven pairs in `colors/colors.json`, equal to the account colours of the
    theme), Today's start screen opening with the day's events, the
    installation's holidays and birthdays. A personal calendar (Gmail over Google's older
    CalDAV at `www.google.com/calendar/dav/<address>/` with the app password,
    Outlook.com over Graph's `/me/calendars` and events delta with
    `exceptionOccurrences`, only those Graph lets the user edit) is taken once
    and is ours afterwards; the organisation's calendar (Traveler's folder of
    type 8, the whole of it with `FilterType` 0, its time zone read from the
    `TIME_ZONE_INFORMATION` blob) is read-only here, refreshed in the sync
    loop, and only its colour is the user's. Public holidays and the weekend
    come from python-holidays (MIT; it caps python-dateutil below 3 only ahead
    of that release, so `backend/overrides.txt` holds dateutil at 3.0 when
    locking) for the country, and the region where holidays differ by region,
    the administrator chooses on the installation's Days off page (Croatia by
    default), computed, not fetched; the same page keeps the company's own days
    off (a collective leave, a day bridging a holiday and a weekend), typed in
    or taken from an iCalendar file after the administrator picks its events,
    and those show with the holidays. The grids tint every day off (weekend,
    holiday, closed day) and colour its number, the small month too, which asks
    `/api/calendar/days-off` for the month it shows. Every change to them gives each series
    that minds days off a new revision, so a phone fetches where its
    occurrences fall now. Birthdays come from the address book. The backend expands every series (`dateutil`'s rruleset on the
    event's own clock, all-day as dates) for the window the browser asks for in
    its own zone, so the browser only reads; an occurrence changed alone
    becomes an override, "this and following" splits the series with an
    `UNTIL` and moves the overrides after the split along, a series moved as a
    whole takes its exceptions with it. A series says what it does when its rule
    falls on a weekend or a holiday (held anyway, skipped, or moved to the
    nearest working day before or after); the backend applies it as it expands,
    and writes it out to a phone and an invitation as plain exceptions (`EXDATE`
    and a moved occurrence, ten years ahead), since no other calendar knows such
    a rule; what a phone PUTs back of those comes home as the rule alone.
    A phone reads the same calendars at
    `/dav/calendars/<user>/<calendar>/` (found from `/.well-known/caldav`,
    `calendar-access`, calendar-query with a time range, calendar-multiget,
    sync-collection), signed in with the same app password as the address
    book; an event it writes is kept as it sent it (`icalendar`), a read-only
    calendar refuses its PUT with 403. An ActiveSync account connected before
    the calendar existed reads its folders once more (a data migration, as the
    address book had), or Traveler never names its calendar folder. Today took
    the shape of D17's mockup the same day: the panel with the month and the
    calendars, the schedule with the "now" line and the meeting under way or
    next, which also stays at the foot of the rail with its link where its
    place is one; tasks and the mail awaiting an answer join as their modules
    land (S4-3, S3-5).
  - *S4-3a, invitations, built 2026-10-26.* The calendar part a message carries
    (iMIP, RFC 6047) is read as the message is taken: a meeting the user is
    asked to goes into a calendar of their own awaiting their answer, a change
    moves it (an older sequence is ignored), a cancellation marks it or the one
    occurrence cancelled, an attendee's answer reaches the meeting the user
    called, and a counter-proposal is only shown. The message shows the
    meeting as a card with Accept, Maybe and Decline, and the event's dialog
    the same; Today marks what awaits an answer. The answer goes back as an
    iMIP reply by mail from the account the user was asked at, in their
    language; a meeting of the organisation's calendar is answered on its
    server (ActiveSync MeetingResponse on the calendar item), which tells the
    organizer itself. HCL Traveler's notices of a meeting carry no usable
    calendar part (a Java array printed where the iCalendar should be, no file
    reference), so an invitation of the organisation is answered from its
    calendar, not from the mail.
  - *S4-3b, invitations sent, free/busy, rooms and tasks, built 2026-10-26.*
    An event with people on it is a meeting the user calls: each of them gets
    an iMIP request by mail from the user's account, in the user's language,
    an update when what matters changes (title, place, time, repetition,
    status; a reminder changes nothing for them), a request alone when they
    are added, and a cancellation when they are dropped or the meeting is
    deleted, one occurrence or the series; the user's own addresses are never
    invited. Who is free is known only inside the installation: a person is
    busy when a calendar of their own has a busy, undeclined event at that
    time (`GET /api/calendar/free`); anyone outside shows as unknown, and the
    organisation's directory is not asked (HCL Traveler answers no
    ResolveRecipients). Rooms, equipment and vehicles are resources an
    administrator keeps (`/resources`); an event books them by carrying them,
    a resource is never on two events at one moment (409 `resource_taken`,
    checked a year ahead for a series), a retired resource stays on the
    events it has and can be put on none. The calendar shows a resource's
    bookings among the events when the user ticks it in the panel, by whom
    and for what, without opening. A task is a note (D17): a line with a due
    date if it has one and done, in the one list (`/tasks`), on its day in
    the calendar and on Today among what is due; it is made from a message
    (the reader's button), a meeting (the event's dialog) or a line of a
    document (the editor's context menu, leading back to the block) and
    leads back to its source. Tasks are PONISTRA's own and not served over
    CalDAV as VTODO; a phone sees them in the browser.
  - *S7, outside agents (D18), built 2026-10-26.* PONISTRA is an MCP server at
    `/api/mcp` (streamable HTTP, stateless, JSON answers), served by the MCP
    Python SDK inside the one ASGI app beside Django and the rooms, and the
    OAuth authorization server its clients sign in at: the metadata under
    `/.well-known/oauth-authorization-server/api/agents` (and at the root) and
    `/.well-known/oauth-protected-resource/api/mcp`, dynamic client
    registration, PKCE, tokens bound to this installation's server (a sign-in
    for another resource is refused), access tokens for an hour and refresh
    tokens for thirty days, rotated; only digests of tokens and client secrets
    are kept. The doors are the SDK's own handlers over our store
    (`apps/agents`): a sign-in waits ten minutes at `/agents/consent`, a page
    naming the client, the user it would act as, where it returns to and what
    it can do, answered Allow or Deny. The account menu's *Agents* lists the
    clients let in, with the server's address to give a client, when each was
    connected and last used, and revokes one: its grant stays as history, its
    tokens go, its next call gets 401. The tools are what the user can do: who
    they act as, search, folders, reading a document or a tab (each block's id
    before its text), creating a document, the operations' JSON Schema and
    `edit_tab` over them, every registry action that takes a tab (a model's
    action runs in the background under the installation's AI switch and the
    user's consent, read back with `get_run`), a message with its text, `list_mail`, `draft_reply`
    and `draft_mail`, calendars and their events, an event created without
    attendees, tasks and contacts. Everything written is a run carrying the
    grant: an agent's edit lands as proposals authored "Claude via Ivo", the
    run bar and history name it so, and a reply it drafts waits on the message
    as a card the user opens in the composer and sends by their own hand (gone
    once the message is answered). Nothing deletes or sends. The installation's
    public address (`PONISTRA_PUBLIC_URL`, which install writes) names the
    issuer and the resource. Not built: a comment tool, since
    pycrdt's `XmlText` gives no sticky index for a comment's anchor.
  - *S2, meetings and chat, decided 2026-10-28* (Ivo: "ok, slažem se"). Meetings
    come before chat, in this order:
    - S2-1: meetings in the installation: LiveKit in compose, a meeting at its
      own link, our call page, the calendar's meeting and its link to join;
    - S2-2: guests by link with a lobby, and the relay (LiveKit's TURN on UDP
      3478 and TLS on 443) for networks without the UDP port;
    - S2-3: chat: channels, direct messages, threads, mentions, files from the
      tree, presence, read within the installation, the one search, a call
      from a channel;
    - S2-4: Web Push;
    - S2-5: recording (our own recorder, decided 2026-11-11);
    - S2-6: the transcript made into minutes with tasks, through D28;
    - S2-7: an external TURN service for an installation without a reachable port.
  - *S2-1, meetings, built 2026-10-28.* A meeting is a room at its own link,
    `/meet/<id>` under the installation's public address; anyone signed in to
    the installation joins it, each joining its own participant (the user's id
    and a random suffix), so one user joins from several devices at once. The
    backend signs a token for ten minutes (HS256, the room and nothing more)
    and asks LiveKit's room API who is in, so the page before joining names
    them; it holds no webhook. LiveKit runs on the host's network: it offers
    the browser the host's local addresses and the public one STUN finds, and
    at start checks the public one answers on its UDP port. The browser asks
    for the camera and microphone once, shows the picture and lets each be
    turned off or switched before joining; inside, the tiles follow the number
    of people, a shared screen takes the stage, speakers are ringed; while LiveKit
    reconnects the page says so, and where it cannot, offers to join again. An event's *Online meeting* is a link of
    its own (iCalendar's `CONFERENCE`, RFC 7986, read also from Teams' and
    Google's own properties, from Graph's `onlineMeeting` and ActiveSync's
    `OnlineMeetingExternalLink`): *Add a PONISTRA meeting* makes one, whose
    page then takes the event's name; the link reaches attendees in the
    invitation's text and its iCalendar, and a changed link is an update. A
    meeting is an event, so the calendar's header keeps *New event* alone. The
    rail's *Chat* holds the conversations and *Meeting now*; a wide screen
    opens the conversation last open in that browser. A planned meeting is
    joined where its event is: Today, the event itself and the foot of the
    rail. Health asks LiveKit whether it answers.
    A planned meeting asks people through its event's attendees; a meeting
    made now has *Add people*, before joining and inside. Colleagues of the
    installation, found by their sign-in or any mail address of theirs, are
    rung in every PONISTRA of theirs that is open: a card over whatever page
    they are on, with a chime once they have used the page, for 45 seconds or
    until they answer; *Join* puts them straight into the call, *Decline* says
    so. Everyone else is sent a link of their own from the user's mail account,
    in the language they read PONISTRA in, which lets them in as guests (S2-2). The
    dialog copies the link and shares it where the device can; the call shows
    each colleague's ring as ringing, declined or unanswered, rung again from
    there. The recipient field offers the installation's colleagues to mail
    as well. The rings travel on the live channel, one WebSocket a tab at
    `/api/live` that S2-3's messages use too: a change tells the users it
    concerns on a Postgres channel, each process listens once and wakes its
    sockets of those users, and each socket reads its user's state again and
    sends it when it changed, so a lost notice costs nothing but a wait.
    The same socket tells a tab which areas of its user's data changed
    (contacts, calendar, tasks, nodes, vault, mail, account, users), however
    they changed: a web tab, the phone's app, CardDAV, a sync or a job. A
    trigger on each table the interface shows (`collab/0006_changes`,
    `FOLLOWED`) names the area and whose rows they are: a user, a node and
    the folder it lies in, a group, a vault collection, a calendar or
    everyone; the process resolves them to users (`live.audience`), and the
    tab reads again what it shows of those areas (`frontend/src/followed.ts`,
    `AREAS`), at most once a second each. An item open in a dialog is only
    marked stale and read when opened again, as one deleted elsewhere would
    answer 404 under it; a socket that comes back after it was lost reads
    everything. The 30-second and 5-minute polls of mail, drafts, the day,
    links, folders, app passwords and company folders are gone (2026-11-05);
    what watches a running job (OCR, runs, health, a meeting) still polls.
    livekit-client 2.23.0 leaving a call while a negotiation is still queued
    offers on the connection it has just closed and warns of it;
    `frontend/patches/` returns that offer quietly, a connection closed by
    anything else still warns.
    *S2-2 guests, built 2026-10-29* (Ivo: "trebamo omogućiti bilo kojoj
    pozvanoj osobi ulaz na call"). A meeting's link opened by someone not
    signed in is its door: the meeting's name, their camera and microphone,
    *Your name* and *Join*, and *Have an account? Sign in* for a colleague on
    a device of theirs. Someone asked by mail from *Add people* comes by a link
    of their own (`?guest=<key>`, the same one each time they are asked) and
    is in at once, under the name they were written to by or give. Anyone
    else with the link waits at the door until anyone of the installation in
    the meeting's conversation lets them in or declines them, beside the
    rings, before joining and in the call; the guest waits on a socket of its
    own (`/api/lobby`), told on the same live channel, and a page closed at
    the door leaves nobody to let in. A guest is in the call as a participant
    marked *guest*; they see, hear and share a screen, and read and write the
    meeting's conversation beside the call, under their name marked *guest*
    (Ivo, 29.10., after the first real call, where the guest never saw what
    he wrote: "tko je pušten u sastanak, mora vidjeti i razgovor"). A guest
    talks by the key of their link while they are in the call with someone
    of the installation, and reads only what was written since the meeting
    began: a meeting held in a group's conversation shows them nothing the
    group said before it, and nothing once the installation has left. Their
    door socket stays open in the call to tell them the conversation moved,
    and how much of it they have not read.
    *The meeting's own window, built 2026-10-29* (Ivo: "da možemo nastaviti
    raditi u scriptoru"). On a computer every way into a meeting (*Meeting
    now*, *Join* in a conversation, the calendar or Today, answering a ring)
    opens it in a window of its own beside the app; joining a meeting whose
    window is open brings that window forward and keeps its call, and *Back*
    there closes it. Once the user lets the app place windows on their
    screens (the browser asks once, from *To another screen* in the call),
    the window opens on another screen than the app's, the largest, filling
    it; *To another screen* moves it to the next one, or shows the meeting
    full screen there where it is a tab. A browser that keeps the window from
    opening gets the meeting in the page itself, which says so and asks for
    pop-ups to be allowed; a phone opens it in the page. Whoever shares their
    screen sees a notice where it would be shown, as a screen showing itself
    repeats inside itself, and the meeting's own tab is not offered to share.
    *S2-2 relay, built 2026-10-29.* A network that reaches neither UDP 7882
    nor TCP 7881 goes through LiveKit's own TURN: on UDP 3478, and as TLS on
    TCP 443 under a name of its own (`PONISTRA_TURN`, DNS only, straight at the
    installation's public address), where LiveKit always offers it. That 443
    is the installation's front: Caddy, built with caddy-l4 (Apache-2.0,
    pinned while it is experimental), reads the name a connection asks for,
    ends TLS to the relay's name with the certificate it keeps for it and
    hands what is inside to the TURN on plain TCP 5349 (`external_tls`);
    every other connection, the challenge that fetches that certificate
    included, reaches the app as before. Caddy takes every certificate through
    443 alone (TLS-ALPN), as the relay's name is forwarded nothing else. The
    router forwards TCP 443 and UDP 3478; the relay's own range needs none, as
    S0 showed. On LXC 210, whose
    app comes through the Cloudflare tunnel, the same Caddy runs alone on 443
    (`ponistra_relay`). The health page asks the relay a STUN binding under
    its name, the way a browser outside reaches it, so an address gone stale
    or a certificate that did not renew shows. A line whose public address
    changes is followed by the installation itself (Ivo: "pa treba pratiti u
    proizvodu"): LiveKit, which reads the address only as it starts, stops once
    STUN names another and Docker starts it again on it; where Cloudflare keeps
    the names pointing straight at the installation (the relay's, and the
    app's where Caddy ends its TLS), the backend points their A records at the
    address every two minutes with a token for their zone
    (`PONISTRA_CLOUDFLARE_TOKEN`).
  - *S2-3, chat, begun 2026-10-28* (Ivo: "kreni"), in four steps: a meeting's
    conversation (S2-3a), direct messages and groups started from people, and
    one's own message edited or taken back (S2-3b), channels, threads and
    mentions (S2-3c), then files from the tree (and what another app shares,
    D26-4), presence, read by whom within the installation and the one search
    (S2-3d).
    *S2-3a, built 2026-10-28.* A conversation is a row in Postgres with its
    members and its messages, plain text as a comment is. Every meeting is made
    with one: its organizer is in, so is everyone who joins and every colleague
    rung, answered or not, and it stays once the call ends. *Meeting now* makes
    its meeting only once it is used, joined or people asked into it, so one
    left before that leaves nothing behind; it has no title until the user gives
    one. In the call *Messages* opens it beside the tiles (instead of them on a
    phone) and counts what is unread; *Chat* lists the conversations someone has
    written to, the latest first, with the last message and what is unread, one
    without a title named by its other people; the rail counts it all, and a
    conversation's page names its people and joins its meeting. A message
    wakes its members' tabs on the live channel, whose state carries each
    conversation's last message and unread count; the tab fetches the messages
    themselves fifty at a time, earlier ones on asking. A member's read is the
    last message they have read, set while the conversation is in sight and
    never past its last message.
    *S2-3b, built 2026-10-28.* A conversation is started from people: *New
    conversation* in *Chat* takes the installation's colleagues alone (found
    by name or sign-in as one types, `/api/conversations/people`), and with
    one of them and no name it is the conversation the two have, started once
    and found again by either; with more, or under a name, it is a group. A
    conversation knows its kind (a meeting's, between two, a group); the ones
    started from people are listed from their start, a meeting's once someone
    has written. A group's people bring colleagues in, change its name or
    leave it (the last one out takes it along), and a meeting's conversation
    takes people and is left too; the one between two stays as it is. *Meeting
    now* in a conversation makes a meeting in it under its name and rings
    everyone else in it, so a direct conversation's call rings the one person;
    a meeting's conversation joins its room instead. One's own message is
    edited, marked *edited* for everyone, or taken back, gone for everyone, from
    the actions beside it; the conversation carries when it last changed, so a
    tab reads the messages again whenever a message is written, edited or
    taken back, not only when a newer one arrives.
    *S2-3c, decided and built 2026-11-08* (Ivo: "kreni prema preporukama"). A channel
    is a lasting, named place with threads that tells you only of what concerns
    you; direct conversations, groups and a meeting's stay flat and announce as
    before, as otherwise every message of a channel of fifty would ring fifty
    phones. Any colleague founds one, with no roles: every member brings people
    in and renames it. *Open:* its name is the installation's alone, every
    colleague finds it under *Channels*, reads it without joining and joins with
    one press; it stays when everyone has left, for its history is the
    company's, until its founder or an administrator deletes it. *Private:* it
    exists only for its members, is entered by a member's *Add people* and goes
    with the last one out. A channel starts no meeting, as it would ring everyone
    in it. *Mentions:* `@` offers the conversation's members, and in a channel
    `@svi`/`@all`; the message stays plain text, with `@Name Surname` in it, and a
    `Mention` row says who it names, so a name changed later touches nothing. In
    a channel a phone and the number on the rail hear only of a mention, of
    everyone named and of a reply in a thread one follows, while an ordinary
    message only marks the row; one message makes at most one notice, and an
    edit tells only those it newly names. *Threads,* in channels alone and one
    level deep: a reply is a message with a parent, the channel shows the number
    of replies under the message and the thread opens beside it, in its place on
    a phone. A thread concerns the author of its message, whoever replied and
    whoever a reply names (`Follower`, with a read of its own). A conversation's
    row is followed (`o:id`, resolved to its members, or to everyone for an open
    channel), so whoever reads an open channel without being in it sees it move.
    *S2-3d, built 2026-11-09* (Ivo's brief on the plan; a channel's meeting decided the
    same day). A message carries up to twenty files and may say nothing else. Bytes from a
    computer belong to the conversation (`chat.Attachment` over a blob, which keeps them from
    the collector), and "Save to folder" makes them an ordinary item. A file of the tree is one
    original: the members get an ordinary read `Grant`, visible in the file's access and tracked
    in `chat.Given`, so joining, leaving, or taking the message back settles it and a grant someone
    gave by hand is never touched. Only the owner of a file may hand it over, as in the access
    panel; a vault folder never lets one go. A guest gets the conversation's bytes through their
    key and nothing of the tree. A link to an item shows as its card only to those who may read
    it. HTML among the bytes is saved, never shown. Read by whom is the members' `read` mark, for
    direct conversations, groups and a meeting's, not for a channel, where it would be a list of
    fifty. Presence is who has `/api/live` open, which holds while one server process serves it.
    A channel's meeting rings nobody: it is a message with "Join", and whoever joins becomes a
    member of the channel. Messages join the one search box as a group of their own, for
    conversations the user is in and open channels.
  - *S2-4, Web Push and the installable app, built 2026-10-28* (Ivo: "kreni sa
    svim sad", asked why the browser offered no install and whether the phone
    and the desktop would be told of what arrives). The app is installable: a
    manifest at the root (`id` /, standalone, the brand icons, one maskable,
    all emitted by `vite.config.ts` from `src/assets/brand`, served from there
    in development) and a service worker at `/sw.js` (`src/sw.js`) that caches
    nothing, so the app never comes from a stale copy: it shows what is
    pushed, unless a window of the app is visible (the open app shows it
    itself), and a click focuses the open window and has the router open the
    notice's page, or opens one. Settings → *Notifications* turns this
    browser on or off, lists the user's browsers with when each last heard
    (another one can be removed, and lets go of its subscription when it next
    opens), offers the install where the browser does (Chrome and Edge raise
    `beforeinstallprompt`; Safari, iOS included, has it in its share menu, and
    an iPhone gets notifications only from the app on the Home Screen), and
    for an administrator the installation's switch (`apps/push.Setting`; off,
    the notices waiting go and no new one is written).
    `apps/push`: `Keys` is the installation's VAPID pair, made at the first
    ask; a `Subscription` is a browser's endpoint and keys with the language it
    reads PONISTRA in, kept by `POST /api/push/subscriptions` and sent again
    each time the app opens; a `Notice` is the facts of one kind for one user,
    worded for each browser in its language as it is sent (`notices.worded`:
    mail is the sender and the subject, a message the conversation and
    "who: what", a ring "who vas zove"). What tells: mail `taking.took` with
    `fresh` (IMAP `caught_up` and an ActiveSync sync that is not a folder's
    first; never the older mail taken in between), kept now, unread and in an
    inbox; a conversation's message to its other members (Topic per
    conversation); a ring to the rung, urgency high, TTL as long as it rings.
    A notice is written only for users with a browser subscribed, and the
    channel `push` wakes `notices.deliver` (the lifespan loop, `drain`), which
    takes one notice at a time with SKIP LOCKED, posts it to each browser
    (RFC 8291 aes128gcm with `cryptography`, held to the RFC's test vector;
    VAPID ES256 with PyJWT, `sub` the first administrator's mailbox; no
    pywebpush), forgets a browser answering 404 or 410, and tries a failed
    one again a minute later, three times, never past the notice's TTL. The
    push services of the browsers (Google's, Mozilla's, Apple's) carry the
    notice encrypted to the device: the one thing that leaves the
    installation besides the AI, and the administrator's switch stops it.
  - *S2-5 and S2-6, recording and minutes, built 2026-11-11* (Ivo: "vlastiti
    recorder"). LiveKit's Egress was the plan and is out: its image carries
    GStreamer built with `gpl=enabled`, gst-plugins-ugly, x264 and the
    non-free fdk-aac. The `recorder` service is ours, in Go over LiveKit's
    server SDK, pion and ebml-go (Apache-2.0, MIT; every module of its build
    permissive, checked with go-licenses). It joins a meeting's room as a
    hidden participant with LiveKit's `recorder` grant and writes what each
    participant sends as it was sent, nothing decoded or encoded: Opus and
    VP8 into a WebM file a track, its duration and index written at its end,
    so a player seeks in it; another codec is noted and skipped. A
    microphone is also cut into utterances at its pauses (by the size of its
    Opus frames: a pause of 800 ms, of 250 ms past 30 s, at most 60 s, an
    utterance under 400 ms of speech dropped), each a file of its own, so the
    transcript knows who said what and when without a model to tell voices
    apart. The recorder keeps a recording on its own volume, noting each part
    as it is made, so a recording a restart cut off is ended from its notes,
    until the backend has taken it; it answers only the backend, on the
    `record` network, which reaches the host's LiveKit. A member in the call
    starts and stops it; the room's metadata tells everyone in it, guests
    too; a room empty for a minute ends it, the recorder telling the backend
    with a key of the recording's. A job then takes each track into a folder
    at the top of the starter's documents, which the members who took part
    may read, and writes the minutes (D28): only the speech of those who
    agreed, a member's standing consent to speech to text unless refused in
    the call, a guest's or a member's answer in the call; each utterance read
    on its own, the names in the meeting given as its vocabulary; Claude
    writes from the transcript the summary, the decisions and the tasks, each
    task to the member it names or else to the starter. The minutes are a
    document in the folder (`operations.write`, tasks as a checklist, the
    people present, the transcript) and the tasks are tasks, sourced from
    the document. Without the model, the minutes are the transcript alone;
    a saving that fails keeps the recorder's files and is saved again by
    its starter from where it stopped. The meeting's page lists its
    recordings, plays a recording's tracks together on one clock, and opens
    its folder and minutes.
  - *S2-7, an external relay, built 2026-11-12* (Ivo: no VPS anyone has to
    keep). An installation behind a firewall or a carrier's NAT opens no port
    inward, so a guest outside gets signalling through the tunnel but no
    media. Settings → Meetings, for an administrator, names a TURN service
    outside: Cloudflare's by a key's id and API token, from which the backend
    mints credentials of a day for each joining (anew once less than 12 hours
    are left, so a meeting never outlives them; port 53 dropped, as browsers
    refuse it), or another provider's by its turn: addresses, user name and
    password. The token or password is sealed like the installation's other
    secrets. Each joining, a member's or a guest's, gets those ICE servers in
    place of LiveKit's own; LiveKit answers the relay outward, offering the
    public address STUN finds even where it cannot confirm it. A relay set but
    not to be had refuses the joining loudly (503 with its reason) rather than
    letting it in without one, and the health page follows it. The proof,
    browsers only through the relay against a LiveKit with no port inward,
    runs through Cloudflare once its key is entered on production; production
    without its port forwarding is a step of its own after it.
- **D16: sheets at scale — closed 2026-10-20** (Ivo: "idemo sa sva tri
  koraka"). Measured on a 616 kB workbook of 11 sheets and 24,000 formulas: one
  tab whose Yjs state was 17.2 MB, 17.7 MB to the browser and 9–15 s on every
  open, 31 s to import; one sheet held 65 % of it, its 17,159 formulas written
  one by one where Excel shares 176. The text stays as D8 has it; the grid
  leaves Yjs. Built in this order, each part replacing what it supersedes:
  - *Rows in Postgres.* A table's columns (ids in order, widths, looks) are its
    `Grid`, each of its rows a `GridRow` (the row's id, its index, height and
    look, and its cells as one object by column id: what was typed, the formula
    as the server keeps it, the look, the merge, the value the server computed
    and its kind). They replace the table's map in the tab's Yjs state and its
    `widths`, `heights` and merges. The text keeps the table block and, as nodes,
    only the cells whose content is more than one line of plain text with one
    look (paragraphs, lists, mixed marks, notes, comments, proposals); every
    other cell is light. The browser asks the tab's grid socket for the rows it
    shows and a margin around them and receives each change to them, so a sheet
    of 100,000 rows opens as one of 100 does; print and export read every row on
    the server. An import takes a workbook of up to a million cells and refuses
    a larger one (measured 2026-10-27 on one sheet of a million plain cells: 61 s
    and 1.6 GB to import, 17 s to open, 1 GB held while in use, 0.1 s to compute
    a changed cell); a cell the importer brings as plain text rides in its
    grid's `texts`, not as a node of its own. A change to the grid is an operation the server orders, applies,
    computes and sends on (cells, looks, rows and columns put in, removed or
    moved, sort, merge, sizes); the browser shows its own at once. A formula
    arrives as typed, in A1, and the server turns it into pieces by row and
    column id (D4) and gives the browser its text; the ids never leave the
    server. Two people writing one light cell: the later write stands, as it
    does in a Yjs map now; text in a node cell merges as all text does. Undo
    takes back one's own grid operations by their inverse, in one history with
    the text's steps; a run keeps its operations, so it can be taken back.
    Versions keep each grid in content-addressed pieces of 256 rows, shared
    between versions where unchanged. Search reads the rows' words.
  - *The workbook is the document.* Every table of every tab computes in one
    IronCalc model per document, live on the server while the document is in
    use: built from the rows once, changed cell by cell, never rebuilt for a
    keystroke. Defined names are the document's. A reference to another table
    carries its id, in whichever tab that table is.
  - *A sheet is a tab.* An imported spreadsheet makes a tab per sheet, named
    after it, holding its table under the same name and its charts. A cell's
    address is its tab's and the cell (`…/tracking/2044?cell=B4`); the name box
    shows `'2044'!B4`.
  - *Compact cells.* A look is an entry of the document's table of looks,
    referred to from a cell, a row or a column, as Excel keeps its styles (a
    formatted column is one entry); a cell shows its own look, else its row's,
    else its column's. A reference to the formula's own row or column is kept
    as such, so a formula filled down is the same pieces in every row and is
    stored once.
  - *Drawn on a canvas* (Ivo, 2026-10-20). The light cells, gridlines,
    headings, selection, fill handle and frozen lines are painted on a canvas
    from the rows the browser holds; the cell being edited and the node cells
    are DOM in their places over it. A cell's fill (its look's, a node cell's
    `fill`, a whole row's or column's that its cells follow) is painted under
    the gridlines, of node cells too, and the selection shows over it as a tint;
    Word's cell shading, PowerPoint's and Excel's solid fills come over and go
    back out as such. The browser paints and computes nothing.
    IronCalc's `worksheetCanvas.ts` (MIT/Apache-2.0) is the starting point,
    reading our rows through an adapter instead of an engine. Print and export
    read the rows on the server, so the canvas never reaches paper.
  - *Only what a change reaches computes* (Ivo, 2026-10-20). IronCalc 0.9.0
    evaluates every formula of the workbook on each change; measured on the
    server, 24 ms for 24,000 formulas, 130 ms for 240,000 and 5 s for 240,000
    with 1,200 running sums. Our patch in `backend/patches/ironcalc/` keeps
    which cells each formula reads and after a change evaluates only the cells
    it reaches, as Excel does; the stored values, the grid socket and the
    browser do not change with it. Built after the browser.
  - *T1 built 2026-10-20:* the rows in Postgres, the workbook per document and
    the canvas, in that order; a sheet as a tab, compact cells and the patch
    follow. Merging is a `span` on a cell of `cells` (a 1×1 span splits; the
    cells it covers are removed). A table referred to by a formula elsewhere
    keeps a name: the server refuses to take it away (`name_needed`), and the
    name dialog, which asks the grid socket what refers to the table
    (`referred`), keeps Save disabled while the name is empty. A table's frozen
    rows (`frozen`, the id of the last one) stay atop the view while it scrolls
    and are its header rows everywhere else: drawn again atop each page the
    table runs onto in the Pages view and in print, where they and the next row
    fit, and Word's `w:tblHeader` both ways. Rows and columns are hidden and
    shown again from the Table menu (`grid` with `hidden`; a row's flag is on
    its `GridRow`, a column's in `Grid.cols`): a hidden line keeps its height or
    width for when it is shown, is a bar across the headings, is passed over by
    the arrow keys and is left out of print, Word and PowerPoint; SUBTOTAL
    101–111 leaves its rows out, and Excel's hidden rows and columns come in and
    go back out as such (2026-11-02). The fill handle drags a range on
    (`fill`): numbers by their trend, dates by a day or by the months between
    them, text ending in a number counting on, anything else repeated, formulas
    moved; it stops before merged cells. Ctrl+D and Ctrl+R fill down and right
    from the first row or column of the selection as copies, as in Excel.
  - *T2 built 2026-10-21:* the workbook per document and only what a change
    reaches computing. The document's defined names are rows of their own
    (`Name`), a table's name is unique in the document and a formula refers to a
    table of any tab. A table stands where its block is in a tab's text, which
    the book reads from Yjs, a live tab's as it changes and an idle tab's from
    its store; a table taken out keeps its grid, so taking the step back brings
    its cells back, but it computes no more, frees its name, and the formulas
    referring to it show `#REF!`. A table brought back under a name another took
    meanwhile is named as a copy is (`Ulaz (2)`). A change enters only the cells
    it touched; lines put in or taken out, merges, and a table that came, went or
    was renamed enter that table whole and the formulas referring to it again.
    The workbook is built at the first change, not when the book is read, and
    the charts over a table are drawn as it changes, into a live tab's room or an
    idle tab's store. Measured on ten tables of 12,000 rows, 240,000 formulas:
    the build takes 2.9 s, the first change after it 140 ms (what each formula
    reads is indexed), every other 0.5 ms. That needed IronCalc's raw model to
    switch its locale without evaluating (patch 0013): formulas are entered in
    the canonical locale, and each switch evaluated the whole workbook and
    dropped the index.
  - *T3 built 2026-10-21:* each sheet of an xlsx, ods or xls file is a tab under
    its name holding its table and charts, in the workbook's order; a chart sheet
    is a tab of its charts. Imported into an open document the tabs follow its
    own, a tab renamed with its table where the name is taken (`Cijene (2)`).
    Tabs imported before T3 stay as they are. An address is `?cell=B4` in a
    tab's first table, `?cell='2044'!B4` in another; a search hit and "Copy link
    to this place" in a table give one, and the table scrolls to it across as
    well as down. The name box opens the toolbar in a table from 768 px wide,
    and with the menu of the place the user is in (table, image, chart…) stays
    in the row while the other segments go under ⋯. It shows the selection as
    `'2044'!B4:D9` and takes an address, a table's name and an address (going
    to its tab) or a defined name, which the grid socket resolves (`where`); an
    address outside the table or a name nothing has is said under it. Ctrl+G
    focuses it, or opens it as a dialog where the toolbar does not show it;
    going there is a navigation, so Back returns.
    Export makes each tab's tables sheets with the tab's charts on its sheet,
    and a tab of charts alone a sheet of its own.
  - *T4 built 2026-10-21:* formulas and looks are kept once per document
    (`Shared`), each under a key of its content (part of its sha256) rather
    than a running number, so two edits adding the same look agree on its key
    with no counter between them, and an import or a restored version needs no
    renumbering. Cells, rows and columns refer to them by key; what nothing
    refers to any more is forgotten. A version keeps what it names with it.
    Existing documents were converted in place: on a copy of Tracking the cells
    went from 9.5 MB to 3.2 MB and the version pieces from 1.5 MB to 346 KB, all
    28,744 values computing the same. The grid socket sends each look once,
    before the first message naming it; a formula still reaches the browser as
    A1 text. An xlsx's column and row styles come in as those lines' looks and
    go back as column and row styles; a cell keeps a look of its own only where
    it differs from its line's (a plain cell in a bold column keeps an empty
    one). A line's look is its font, highlight and alignment, not a number
    format, which Tracking's line styles do not have. That needed IronCalc to
    give a row a style only where the file marks it custom-formatted, and to
    list a sheet's styled rows at once (patch 0014). The ponx file is version 4
    and refuses an older one.
  - *T4c built 2026-10-21:* a whole column or row chosen, by its heading or
    because every cell of the line is chosen, is formatted as that line's look,
    as in Excel: the same change reaches each cell of the line that shows
    another look, its own or that of a line crossing it, and a row or column
    added later takes the line's look. The browser works out the change from
    the active cell's look and sends one `looks` operation naming the lines, so
    choosing everything in a long table formats it without its rows being
    loaded. A command a line cannot carry (a list, a heading) is disabled there.
- **D17: the suite's frame and TaskStreamer — closed 2026-10-23** (Ivo: "želim
  da scriptor bude kompletna aplikacija i samostalna, al da s integracijom s
  taskstreamerom dobije još više na snazi").
  - *Frame* (mockup accepted 2026-10-23, Ivo: "sviđa mi se, idemo u tom
    smjeru": https://claude.ai/artifact/2vRxMBMeM7B3gvMmbon5gF). Left of D9's
    panel, a narrow rail of modules in the order of a working day: Today,
    Calendar, Mail, Documents, Chat. Today is the start screen: today's meetings
    and the tasks due, mail awaiting an answer, the documents last worked on.
    The panel follows the chosen module as D9 has it: for Today and Calendar the
    month and the calendars, then accounts and folders, the tree (inside a
    document its tabs and headings), channels. The next meeting stays in sight
    at the foot of the rail with its join button. The rail holds five modules,
    the same on a phone, where it is a bar at the bottom (Ivo 2026-11-02, "i na
    mobitelu imati pet izbornika", replacing the four groups of 2026-10-28):
    Today, Calendar, Mail, Chat, Documents. What is opened less often is a link
    in a module's column, not on the rail (Ivo 2026-11-02): the vault under
    Notes in the documents column, its items still apart from the tree;
    contacts under the conversations; settings only from the account menu and
    the search box. Such a place's header leads up to its module before its
    title (*Razgovori › Kontakti*, Ivo 2026-11-04): the way back is always the
    same, wherever the user came from, and the installed app's window has no
    back button of its own. A row in the side column carries no ⋯ (Ivo 2026-11-04): its menu opens where
    it is, on a right click or a long press, as a mailbox, a mail folder, a tab, a version, a folder of the tree, a calendar, a conversation and a vault's collection do. The header ends the same on every page: the page's own actions, then
    the search box, the microphone and the account menu, so the box and the
    microphone never move. Each page has one filled button, what the page makes (a new
    conversation on Chat, the meeting now beside it outlined); the rail ends
    with the installation's revision, which opens About. The rail is in place now with all five (Ivo: "svih pet,
    nedovršeni onemogućeni"): a module still being built shows and cannot be
    opened. Today starts at `/` with the documents last changed that the user
    can read, and gains each tile as its module lands; the documents moved to
    `/documents`. A page with no side column of its own, as Today until the
    calendar, shows none rather than an empty one. *Mail waiting* (built
    2026-11-02, Ivo: "u today možda trebali imati i mailove"): unread inbox
    messages from people the user has written to (the correspondents, so
    newsletters and notices stay out without a rule) and what the user
    flagged of the last 14 days (flags kept for years in Notes or Outlook
    wait on nothing), five newest with the count leading to the inbox, beside
    the recent documents on their left; like the tasks due, it stays when
    empty and says so.
  - *Tasks are notes.* No hierarchy, projects or workflows. A task (D15) is a
    short note with an owner, a due date if it has one, and done; it is made
    from a line of a document, a mail, a meeting's minutes or a message, and
    leads back to it. It shows on its day in the calendar, in Today and in the
    one list.
  - *Free and whole on its own.* Everything that is office work is in PONISTRA
    at no cost, and nothing in it is held back or weakened to sell TaskStreamer.
    TaskStreamer adds what is a firm's process (workflows, ERP, invoicing, the
    books), not a missing half of PONISTRA.
  - *Chat is not an overlap.* TaskStreamer's messaging stays closed inside a
    company and its records; PONISTRA's chat and meetings reach anyone invited,
    guests by link included. Both stay. The calendar is cut the same way (Ivo
    2026-11-05): TaskStreamer's company calendar holds meetings, rooms and
    free/busy among its own users only, with no invitation, CalDAV or mail
    going outside; PONISTRA's calendar reaches anyone.
  - *The connection.* Off until the administrator turns it on, as AI is (D15):
    a TaskStreamer company's address and an OAuth grant. Every call goes out
    from PONISTRA, since an installation is often not reachable from outside.
    TaskStreamer never starts it (Ivo 2026-11-05): no button, call or webhook
    of its own goes towards PONISTRA, only the API PONISTRA calls.
    Each thing has one owner. Documents are PONISTRA's: TaskStreamer points to
    them by link, makes the documents it generates (offers, contracts) as
    PONISTRA documents, and its Documentation search reads chosen folders in
    place of SharePoint. A note stays PONISTRA's until it is handed over; then
    it is a task of a stream or project in TaskStreamer, and the note shows its
    state, read-only, with a link. TaskStreamer's own tasks, Beats and company
    calendar show in the calendar and Today, read-only. Clients and suppliers are
    TaskStreamer's, by tax number, and show as an address book, read-only. Mail
    is PONISTRA's; a mail is handed to TaskStreamer as a ticket, a document in
    a client's folder or a task. S4 subscribes to an outside calendar by its
    iCal address, which would show TaskStreamer's Beats before the
    connection exists; TaskStreamer serves no such address yet (2026-11-05).
  - *How TaskStreamer shows.* Not at all until the connection is on (Ivo: "ne
    smijemo napadno s taskstreamerom ići nego samo kad se omogući konekcija").
    Until then only the integrations page in the administration, where it is
    connected, and the About dialog name it; users see no action, label, banner
    or dialog of it, and nothing is counted or sent. Once connected, its actions
    join the action registry (D14) in their natural places (a mail's menu, a
    note's, a document's), and its items show as the connection above says.
  - *Licence.* Ivo holds both, so he may also take PONISTRA's code into
    TaskStreamer, which is why outside contributions are not accepted (D15).
- **D18: outside agents — closed 2026-10-24: PONISTRA is an MCP server** (Ivo:
  "slažem se"). Any agent a user lets in, Claude Code, Claude's apps or another
  maker's, works on PONISTRA through the Model Context Protocol. The direction is
  the reverse of D14's AI: there PONISTRA asks a model with the installation's
  key; here the agent calls PONISTRA, and its thinking and its bill stay on its
  side. Agents' memory was weighed and left out: it stays in git and files beside
  the code, and PONISTRA holds documents for people. A code editor came later, as
  the owner's workspace (D34), where the agent's harness stays its maker's.
  - *Tools.* Reading: search (D12), a folder's list, a document or a tab as the
    tagged text a model reads for an action. Writing: a new document, content
    into a tab, a comment, and each action of the registry under its own id, its
    parameters' JSON Schema being already a tool's shape. Mail and the calendar
    join the same way as S3 and S4 land; a reply waits as a draft. Nothing
    deletes.
  - *Through the same doors.* Every write goes through `operations` as a run
    with its changes, checked against the schema, so Undo takes back what an
    agent did as one, and whoever has the document open sees it written live.
    Content an agent writes comes as proposals for the user to accept or
    reject; an action keeps its own review (D14). History names the agent with
    its user ("Claude via Ivo").
  - *Access.* An agent acts as the user who let it in, never beyond that user's
    grants (D11). It signs in by OAuth as MCP's authorization specification has
    it (revision 2026-07-28, read again when S7 starts): PONISTRA is the
    authorization server, the user sees a consent screen naming the client, and
    the account page lists the clients let in, each revocable. Claude Code on
    the same host reaches the backend directly; claude.ai and Claude's apps
    reach it at the installation's public address (D7).
  - *Instructions planted in a document.* An agent reading a document from
    outside may meet instructions written into it. Proposals, Undo and the
    absence of anything that deletes bound what such a document can make it do.
  - *Libraries* (checked 2026-10-24, revised 2026-10-26): the MCP Python SDK
    (MIT, 2.3.0), its server mounted at `/api/mcp` in the ASGI app beside
    Django and the rooms, and its own authorization-server handlers over a
    store of ours; django-oauth-toolkit was rejected, since it depends on
    jwcrypto (LGPL).
  - *Place.* Phase S7, after mail (S3) and before the calendar (S4): its core
    is the registry and operations already built, and OAuth is most of it.
- **D19: tables our way — closed 2026-10-24** (Ivo: "slažem se"). D14's filter
  applied to the table itself. Excel stays the contract: IronCalc, the formulas
  in the model and xlsx both ways are what lets an imported workbook compute as
  it did in Excel and leave with its formulas, so they stay as D4 and D16 have
  them. Excel's surface is no longer copied: the way of working in a table is
  our own, a few choices made in place over Excel's formulas, and an agent for
  the rest.
  - *One engine.* Whatever the choices offer is written as Excel's formulas and
    IronCalc computes it; there is no evaluator of our own beside it, so a
    table made here computes by the rules of one imported and exports as live
    formulas. The user picks "Average", the cell holds `SUBTOTAL(101, …)`.
  - *Totals by choice.* Each cell of the totals row (`table.totals`) offers
    sum, average, count, minimum, maximum or nothing, written as `SUBTOTAL`
    109, 101, 102, 105 and 104; a column of text offers the count of its
    values (103). The row is still recognised by its formulas, now any of
    these over its own column, and computes at once, as D16 computes what a
    change reaches.
  - *The calculated column* (`table.calculate`, A6). A column whose formula is
    given once, in its header: an operation (sum, difference, product,
    quotient, average, minimum, maximum) and the columns of numbers it takes,
    picked by their headers in the dialog ("Iznos = Količina × Cijena",
    "Prosjek Q1–Q4"). The server writes the formula into each row of the data,
    in the number format the first operand shows in, and a row put into the
    data takes the formula its neighbours share. It is recognised by its formulas, as the totals row is: every row of
    the data holds the same formula relative to its row. Nothing is stored
    twice, a workbook whose column was filled down in Excel brings one
    already, and a cell written otherwise ends it, as Excel marks an
    inconsistent calculated column. Export writes each row's formula, which
    every spreadsheet reads. (IronCalc computes all of `SUBTOTAL`'s functions
    and `CORREL`, checked 2026-10-24.)
  - *The agent beside the document.* "Other…" moves from a dialog for one
    request into a panel beside the document: a conversation over the
    selection or the tab ("a bar chart of sales by month", "now as a pie",
    "leave out 2023"), each turn a run with its Undo, its tools the operations
    as A5 built them, under the same consent. It works on text the same way
    ("shorter", "now more formal"). What repeats there becomes a predefined
    action and, where it can, code (D14).
  - *Analysis at scale.* The model does not read a large table cell by cell,
    which at thousands of cells costs much and misleads. It reads a profile
    that code computes (each column's kind, range, empty cells, distinct
    values, a sample of rows) and the numbers IronCalc computes (`CORREL`
    between the columns of numbers, `AVERAGE`, `STDEV`), picks what is worth
    saying, and writes the result into a new tab: a table of those formulas,
    charts over it, and its text. Every number it states stands in a cell as a
    formula; it computes none itself (D14 *AI*).
  - *Frozen.* More of Excel's surface (editors for defined names, conditional
    formatting, validation, pivot tables, dialogs of formats) is not built.
    The import keeps or reports it as D4 says; where one is needed, it is an
    action or the agent's work. Excel's headings, A1 with a click on a cell
    and `$` when copying stay as D4 has them, for whoever types a formula.
  - *Place.* Phase A6, after S3's step *the mail is ours* and before the rest
    of S3: totals by choice, then the calculated column, then the panel. The
    panel's analysis tools are tools S7 exposes as well.
- **D20: company folders, access and the vault — closed 2026-10-24** (Ivo:
  "slažem se s predloženim"). Users work in the company's folders as their
  authorisation allows, the computer is a terminal to PONISTRA, and the
  passwords people use live in PONISTRA too.
  - *Company.* A third root beside My documents and Shared: top-level
    folders owned by groups, which the administrator lays out and assigns
    without reading them (D11). With the work there, My documents is the
    user's own and is not handed to a successor on deactivation.
  - *Access.* A log of who opened, downloaded and shared a node; each user's
    sessions and devices, which they and the administrator can end; a passkey
    policy; and a folder option *no download*, which keeps its documents in
    the browser.
  - *The vault* is a password manager for every user, end to end encrypted on
    Bitwarden's model: unlocked with Argon2id in the browser (WebCrypto), a
    key pair per user, each collection's key wrapped for each member, so the
    server cannot grant access and someone who holds the key confirms a new
    member. A recovery code always; recovery through the company as an
    administrator's policy. Vaultwarden, Passbolt and Bitwarden are AGPL or
    GPL, so it is our own. The secrets the server itself uses (mail, AI,
    OAuth, the off-site copy) stay sealed with the installation's secret key.
    Filling in passwords from a browser extension is a later phase.
  - *TaskStreamer*, when connected, fills the groups from its organisation
    chart, read-only here; the model of rights does not change (D17).
  - *Place.* S1, after the off-site copy: company folders with the log and
    sessions, then the vault.
- **D21: one search over documents and mail — closed 2026-10-24** (Ivo:
  "slažem se sa ovim"). D12 stays the engine; it widens to mail and to the
  attributes of both.
  - *One box.* The box in the top bar searches documents and mail together:
    for mail the subject, body, sender, recipients and the text of
    attachments; for documents what D12 indexes. Filters show as chips under
    the box and can be typed: kind, from, account, folder, period, has
    attachment (`od:ana`, `vrsta:pošta`). This works without AI, on every
    installation.
  - *Groups* (Ivo, 2026-10-24: "automatski pretražuje sve ali grupira
    rezultate"). Every search goes through everything; the hits come grouped
    by module (Dokumenti, Pošta, then the calendar, contacts and chat as they
    come), each group ranked within itself. A filter only one module can meet
    (an account, an attachment, `vrsta:pošta`) leaves the others out.
  - *AI as a translator.* A sentence ("dokument koji spominje taskstreamer iz
    drugog mjeseca prošle godine") goes on Enter to a small model, which
    returns text and filters only (`{text: "taskstreamer", kind: document,
    from: 2025-02-01, to: 2025-02-28}`); they show as the same chips, to be
    corrected, and the same Postgres search runs them. One call per search,
    never per key, through A4's consent: here the user's own, this once or
    for all their searches, a no kept as well, changed in Settings → AI
    beside the speech consent; only the sentence and today's date go out.
    With AI off the box searches the words. The search page carries no
    explanations of its syntax or of the model (Ivo 2026-11-02: "makni ono
    svo pametovanje i pojašnjenja za koja nitko nije pitao"). Its runs count in the AI usage with the
    actions'.
  - *Dates.* A document's period is when it was made, one click turns it to
    when it was changed; a message's is when it came.
  - *Meaning.* Search by meaning (finding "solar" where the word is not used)
    is not built now. If it comes, its vectors live in the same Postgres
    (pgvector, PostgreSQL licence), not in a second engine such as Qdrant:
    rights are filtered inside SQL (D12), and a second store would hold a copy
    of them to keep in step, and one more service for every installation.
  - *Place.* S3: mail into the index and the filters after the bulk actions in
    the list, then the translator.
- **D22: Postgres holds the sheet, our own engine computes it; IronCalc leaves —
  closed 2026-10-27** (Ivo: "ja bih ironcalc skroz izbacio iz igre", "idemo sa
  ovim"). Measured that day on one sheet of a million plain cells, not one
  formula among them: 61 s and 1.6 GB to import, 17 s to open, then 1 GB held
  while in use, 0.7 GB of it the book's copy of rows Postgres already holds and
  0.3 GB IronCalc's workbook. The 76 workbooks of Ivo's work folder hold
  372,084 cells and 11,554 formulas, written with six functions (IF, ISBLANK,
  XLOOKUP, HYPERLINK, SUMIFS, SUM). D19's language stays: a formula is Excel's,
  typed, kept by row and column id (D4), shown and exported as Excel's; only
  what computes it changes.
  - *Postgres is the only store of a grid.* Every cell lives in its `GridRow`
    and nowhere else. The book keeps a table's columns, not its rows or their
    order; the browser's window, sort, filter, find, fill and rows put in or
    taken out are SQL over the rows. A table's size is bounded
    by the disk, not by memory. Between calculations the book keeps each
    formula read, by its key, table and column, for as long as the tables,
    defined names and rows named by id it was read against stand; a value
    typed reads no formula again (one edit among 50,000 distinct formulas:
    4.4 s before, 0.5 s on 2026-11-10). A calculation hands back, of the rows
    it changed, only those a browser holds; the rest stay with Postgres.
  - *One registry of functions.* Each function is defined once, as actions are
    (D14): its Excel signature; its rules (blank, text, errors, rounding half
    away from zero, the 1900 date serials, comparison regardless of case); its
    Python form, which every function has; its SQL form where SQL gives
    Excel's result exactly; and examples with Excel's results. A parser turns
    a formula (hr and en separators) into a tree and a compiler takes each
    node from the registry. Where each of its functions has a SQL form, the
    same formula filled down a column, aggregates over a range and lookups
    compile into one query (`IF(ISBLANK(B2);"";XLOOKUP(B2;…))` down 8,000 rows
    is one join); a chain of cells (A3 = A2 × 1.1, a running balance) and a
    formula holding a function without one are computed by the Python forms
    in the backend, over the rows they reach. SQL is derived on each
    computation and never kept.
  - *Where it computes*, measured 2026-10-27 on a table built as `GridRow` is,
    100,000 rows of ten columns, B×C, ROUND and SUMIF down the rows: SQL in
    Postgres took 0.03–0.08 s, PL/Python 0.09–0.19 s, DuckDB in the backend
    0.10–0.20 s and Python in the backend, the rows fetched, 0.21–0.39 s.
    Writing the column back took 7–9 s whichever computed it: 1.3 s for the
    rows themselves, the rest for the search vector and its GIN index,
    recomputed with every value. What computes hardly matters, so SQL computes
    where its form is exact and Python everywhere else. PL/Python, which would
    put the engine into a Postgres image of our own, gains a tenth of a second
    against that write and is left out; so is DuckDB, slower by the rows it
    fetches and rounding 1.005, 0.285 and 5.015 unlike Excel. Postgres rounds
    a double half to even, so the SQL forms round through numeric. How
    computed values reach search without that write is E2's (below).
    The registry's skeleton comes from Excel's published list: every function
    ECMA-376 Part 1 §18.17.7 defines, with MS-OI29500's notes where Excel
    departs from it, and the newer ones ([MS-XLSX], written `_xlfn.`), each
    with its name, arguments and category, so a name is either Excel's or not.
    The forms are written by us in waves by use, a hundred or so first; most
    share a family's template (aggregates, aggregates under criteria, lookups
    as joins, scalar functions). The rules live in the kind of each argument,
    not in each function, so each of Excel's quirks is written once.
  - *Excel is the reference.* An xlsx Excel saved holds each formula and the
    value Excel computed. The repository's reference is a workbook of cases
    we generate, a sheet per category (blanks, text, errors, rounding, dates),
    which Ivo opens and saves in Excel once per wave, with the examples of
    Microsoft's help pages as cases beside it; no user's files and no other
    engine's test files are used. Both forms of a function must give Excel's
    number. Every import is then a check of its own: our computation is
    compared with the value Excel saved, at Excel's fifteen digits (functions
    that change by themselves, as NOW, TODAY and RAND, and references into
    other workbooks aside), and the cells that differ go into its report,
    inside the installation that imported it.
  - *What a cell shows that we do not compute as Excel did.* On import it
    keeps Excel's value, which is right for the data as saved, marked and
    counted in the report. Once anything it depends on changes, that value no
    longer holds: a function the registry has no form for gives #NAME?, as
    Excel does for one it does not know, and one that differed shows our
    computation, still marked. Nothing computes an approximation.
  - *Files without IronCalc.* xlsx is read row by row (lxml, E4):
    rows go into Postgres with Excel's values and are shown as soon as the
    first are in; the formulas are then grouped into families, by the shared
    formulas Excel itself writes for a formula filled down
    (`ref="C2:C8000"`) and otherwise by the same formula relative to its row
    (as a calculated column is recognised, A6-2), each family computed as one
    query in the order of what it depends on and chains in Python, and
    compared as above. xlsx is written as a stream (XML of our own), each formula
    with our value beside it; CSV imports through the same stream; a table
    longer than Excel's 1,048,576 rows exports across sheets. Number formats
    and typed input in the document's language are a module of our own. Each
    library's licence is checked before it is added.
  - *E2, built 2026-10-27.* A family is a run of rows of one column holding
    one formula relative to its row (`engine/family.py`), computed as one
    SELECT over the table's rows r: a reference relative to the cell reads the
    row r is at, moved as written (B2 the own row, B1 the one above, B1:B3 the
    three around it); one written absolutely is the same for every row and
    Postgres computes it once for the query (`InitPlan`, verified in each
    plan). An area that grows down the family (`$B$2:B2`) and a family that
    reads cells of its own column are Python's. Exact lookups (VLOOKUP,
    XLOOKUP, MATCH) build their range once into a map by key: a number by its
    fifteen digits, text by its lower case where every letter is one whose
    texts the collation (below) holds equal exactly where their lower cases
    are (`sql.COMPARED`: 304 letters of ASCII, Latin-1 and Latin Extended-A,
    derived from the collation when the engine loads, Croatian lJ, nJ and dŽ
    left out), a logical, an empty cell; a text with any other letter may
    match otherwise than by its lower case, so it makes NULL (Python) only
    the rows whose match it comes before, or that find none. SUMIF(S) and COUNTIF(S) whose criterion is computed for
    each row (`SUMIF($A:$A;A2;$B:$B)`, `SUMIF($D:$D;"<="&D2;$B:$B)`) are
    swept (`engine/selection.py`): one query reads the range and the distinct
    sets of criteria the rows compute, and the backend passes over the cells
    once in their order, adding each number with numpy to every set selecting
    it in one array operation. Each set takes its numbers in the order SUM
    adds them, cancelling to 0 where SUM does, so its total is Excel's to the
    last bit, for the cells times the sets that a query for each set would
    pay many times over. A criterion matching one value (`A2`, `"="&A2`,
    `"<>"&A2`) selects by a key: a number by its fifteen digits, text by the
    key two texts share exactly where the collation holds them equal
    (`Collation.equality`); a comparison (`">"&B2`) selects a run of the sets
    sorted by their bound, a number by its fifteen digits, text by its place
    in the collation's order (`Collation.ranks`), a logical as Excel orders
    them. A text whose weight depends on what stands before it, which the
    collation may hold equal to two texts unequal to each other, leaves its
    rows to Python. The
    texts of the criteria and of the range are read by Python on each
    computation (`criteria.operand`, `formats.read`: a date without its year
    reads into the year it is computed in), so SQL never guesses a reading. A
    wildcard, an error as the criterion and a number SQL cannot write as text
    (from 1E+15, below 1E-04) leave their rows to Python. numpy is built from
    source without BLAS (BSD-3): its wheels bring OpenBLAS with libgfortran,
    which is GPL. Measured on 100,000 rows (8,000 codes like ART-00123):
    `IF(ISBLANK(A2);"";XLOOKUP(…))` 0.54 s down 8,000 rows and 1.25 s down
    100,000 (Python 54 s and ~670 s), VLOOKUP 1.2 s, SUMIF 1.9 s, COUNTIF
    1.7 s, SUMIF to a date computed in each row 2.2 s, to an amount 3.9–5.7 s
    and with `"<>"&B2` 9.7 s, SUMIFS by a key and a date 4.0 s and between two
    bounds 16 s (Python ~4 hours, each row reading the whole range), B×C
    0.24 s, ROUND 0.32 s, SUM of the three rows around 1.3 s. Held to Excel's
    own values (every saved case compiled; SQL computes 254 of the Croatian
    1,012 and 253 of the English, the rest NULL or Python, none differing),
    the sweep to a workbook of its own (`tests/sweep.py`, saved by Excel as
    sweep-hr.xlsx and sweep-en.xlsx: 20,000 rows, 11 families, each total
    equal to Excel's to the last of the seventeen digits it saves), and to
    Python on tables drawn at random: 50 families × 300 rows × two draws × hr
    and en, numbers, texts with Croatian, Cyrillic, Greek and other letters,
    blanks, logicals and errors, not one cell differing. Search reads a row's words from
    `GridRowWords`, kept apart from the row: statement triggers queue each row
    written (`StaleGridRow`) and the backend reads their words again in the
    background (`content/words.py`), so writing 100,000 values takes 0.48 s
    instead of 4.5 s and their words follow within seconds. How a cell's value
    itself, not only its text, is kept in `GridRow` is E3's, and the family
    takes the read of a column as given until then.
  - *How Excel compares, matches and halves, measured 2026-10-27* in a
    workbook of its own (`tests/matching.py`, saved by Excel as
    matching-hr.xlsx and matching-en.xlsx: every criterion against every kind
    of cell, every value against every cell in each lookup, a text for every
    character Excel may meet sorted by SORT and put to its neighbours, lines
    of numbers halved). Excel compares text as Windows' CompareString with
    NORM_IGNORECASE in its locale, not as ICU: by the Windows 11 Sorting Weight
    Table Microsoft publishes with [MS-UCODEREF] under its Open Specifications
    notice, which lets anyone copy it to build an implementation, its patents
    under the Open Specifications Promise (`engine/collation.py` derives
    `collation.json.gz` from it and names its URL and sha256). It is no order:
    diacritics are summed in a byte, old Hangul jamo weigh only beside each
    other and the units both texts begin with are skipped first, so a < b < c
    < a happens, and SORT is Excel's merge of runs of one, two, four and on,
    not a sort by a key. Windows weighs Croatian Ǳ, ǲ and ǳ without a caron
    after them as two Tibetan letters, which no section of the table says (its
    Hungarian exception for them reads "get rid of dz bugs"): ǲ as Ba Sa, ǳ as
    Pa O, Ǳ as Da and a weight no letter has, between Nna and Pa; the engine
    takes them as Excel shows them. =, <, COUNTIF
    without a wildcard and XMATCH compare so; MATCH, VLOOKUP and XMATCH with
    wildcards always read the text sought as a pattern, each run of it held
    equal unit by unit, so "ß" finds no "ss" there, and their tilde takes any
    character; a criterion is a pattern only where it holds * or ?, its tilde
    then taking any character too ("~~" is two tildes, "~~*" one and anything),
    and reads a number with only its language's own currency where the
    language writes it ("12 €" in Croatian, "$12" in English; "€12" is text in
    both, though VALUE reads it). MATCH, VLOOKUP, HLOOKUP and LOOKUP look an
    empty cell up as 0, XMATCH and XLOOKUP as an empty cell. Approximate MATCH,
    VLOOKUP and LOOKUP halve the line from the middle, taking the first value
    of the kind sought to its right, and give the last of a run of equal
    values; MATCH -1 goes along the line; XMATCH by halves orders the kinds as
    SORT does and gives the first of equal values going up, the last going
    down, and refuses wildcards (#VALUE!); XMATCH for the next smaller or
    larger value along the line orders the kinds so too, so the next larger
    after 9 may be a text and after "z" an error. SORT takes its index and
    order as INT does (1.5 sorts up, -0.5 down, 0.5 is #VALUE!), puts numbers,
    text, logicals and errors (by their codes) in order or all the other way
    round, keeping equal ones as they stood, and empty cells last either way.
  - *How the grid is kept, decided 2026-10-28*: a reference to another row
    of the cell's own table written relative is kept as how far that row
    stands from the cell's own (D16's `OWN` is the distance 0), one written
    absolute, one to another table and one to a row no longer there by the
    row's id. A formula filled down is then one entry of `Shared` however
    long the column, a row put in, taken out or moved rewrites only the
    formulas that reach across it, and a row is computed from its place
    alone: measured on a million rows in Postgres, a window of a hundred rows
    by `position` takes 36 ms in the middle and 72 ms at the end, numbering
    every row to join references by id 1.6–1.9 s. The book holds the
    columns, not the order of the rows. Migration `content/0010` rewrites
    what was kept by ids; versions and ponx files keep the form of their
    day, the own row having been `OWN` in both.
  - *Changes as SQL, decided 2026-11-07* (Ivo, E3's steps 4 and 5 as one
    cut, since SQL changes beside a grid in memory would have to be mirrored
    into it): every patch is applied as SQL over `GridRow`; a cell's value
    before comes back through `RETURNING OLD`, and rows taken out stay in
    Postgres under the change's token until it can no longer be taken back.
    A range is sent by its ends, never by its rows' ids: a sort, which
    compares as Excel does, a deletion and a fill. A filter is a view, not a
    change: each user's own, kept by user and table (`TableFilter`), set
    from a cell's value or as a column's values or one comparison, and shown
    as chips above the table. A browser is sent only the rows not hidden
    that meet the user's conditions, counted among themselves, each with its
    own place among all the rows as its number, which headings and addresses
    show; hidden rows are left out the same way for every user. A range edit
    (sort, fill, deletion, hiding) reaches only the rows the filter shows,
    and an edit that moves a row in or out of the view lays the table out
    anew in each of the user's browsers. Formulas, printing and export are
    not filtered. Find and replace cover the tab, its text, its notes and its
    tables, the tables by SQL over what their cells show, hidden rows left
    out; a replacement, of one hit or of all, is the operation `substitute`
    and one change; a cell a formula calculates is found but never
    replaced, as its text is the formula's.
  - *What is entered takes Excel's format, decided 2026-10-28*: a text typed
    in a cell takes the number format Excel gives it in the document's
    language, a formula the one it carries from the cells it reads, and a
    cell holding a format keeps it or takes the entered one as Excel does;
    each cell shows its value as Excel shows it, elapsed time and the halves
    of a second included. Held to what Excel gave about 105,000 entries in
    each language (`engine/tests/implied.py`), the last round unseen before
    it passed. One departure (Ivo, "nastavimo po preporukama"): a formula
    entered in a cell formatted as Text stays a formula and keeps the Text
    format, where Excel keeps the formula as its text.
  - *What reads a whole table, decided 2026-11-08* (Ivo, E3). Nothing holds
    a table as a grid in memory but what has to: versions keep values and what
    cells show with their rows and are read by windows of rows; a table's
    actions read it a few thousand rows at a time; a copy of a table is
    Postgres's, its undoing takes the copy out and its doing again copies the
    table as it then stands; the Elements read the rows with a merged or
    styled cell; the print gets the rows as a stream and Chromium holds them
    (its own 4 GB, a visible error past it: pagination needs each row's
    height); PONX is written row by row. A ceiling of 200,000 cells stands
    before what builds one tree of a table: Word and PowerPoint refuse with
    the word to export to Excel, translation and gathering refuse, an agent's
    reading gets the first rows and is told so.
  - *Order*, 4–6 weeks: E1 the parser, the value rules, the registry's
    skeleton and its first wave (SUBTOTAL for A6-1 among them), the Python
    evaluator, the number formats (TEXT, VALUE and DATEVALUE need them) and
    the workbook of cases, read by openpyxl; E2 the SQL compiler under the
    same tests and computed values reaching search apart from their write; E3 the grid only in Postgres, the book without its copy; E4
    the files and CSV, the import with its check. Built in a worktree of its
    own; main computes with IronCalc until the switch, which deletes IronCalc,
    `backend/patches/`, the live workbook and D16's grid in memory in one
    change. A6-2 is finished as it stands, since it writes Excel's formulas;
    A6-3 and A6-4 wait for D22.
  - Once switched it supersedes D19's *One engine*, the IronCalc entries of
    the stack table and the xlsx import's cell limit (D16).
  - *E4, built 2026-11-10; IronCalc, `backend/patches/`, the live workbook and
    the grid in memory are gone.* A sheet streams when its part is over 8 MiB
    unpacked or its declared size over the cell limit (`imports/laying.py`, in
    batches of 5,000 rows; browsers told at most every 3 s), and the job answers
    as soon as the first rows are in. Row and column ids derive from the
    position, so no list of them is held and a formula may name a later row.
    Excel's saved values wait in a temporary table until compared. The reader
    and the writer are XML of our own, in place of openpyxl's read-only mode and
    XlsxWriter, so neither became a runtime dependency. A file's parts are limited
    by what they really unpack to, never by their headers: 4 GiB the whole file
    and 10,000 parts, as only a stream; what is read whole 256 MiB a part (and
    the shared strings) and 2 million nodes; a worksheet's element 32 MiB until it
    closes; the worksheets held as cells 64 MiB together, the others read in
    rows. A file of a few megabytes then holds at most 1.2 GB (measured against
    each way of filling a part: V1). There is no limit on cells. 300,000 rows of 4 columns: opened after 0.3 s, written in 112 s,
    calculated in 18 s, compared in 7 s, peak 1 GB. Calculating reads the rows
    8,192 at a time and keeps at most 65,536 computed values and 64 pages before
    writing them: 300,000 cells holding one formula copied down hold some 35 MB
    (650 MB before). What it keeps in full is each different formula, some
    3.4 kB, so an import refuses a document with more than 50,000 different
    formulas (170 MB in a calculation, measured 10.11.2026) and keeps the file
    as a file, saying so (`too_many_formulas`). A streamed sheet
    keeps no links (reported as lost) and a table design over 200,000 cells
    stays an Excel table but is not drawn. CSV imports by its extension through
    the same laying, each field read as if typed into a cell, and exports the
    document's first table as what each cell shows, `;` where the document's
    decimal is a comma.
- **D23: every file read as far as permitted tools allow — closed 2026-10-27**
  (Ivo: "analiziraj sve ekstenzije", "razmišljaj o drugom korisniku koji može
  imati svašta", "slažem se sa preporukama"). The bytes decide what PONISTRA
  does with a file, its extension names it. What the browser reads itself is
  shown in it; a reader of someone else's format runs in the `converter` or the
  `media` service, apart from the backend, its database and the internet.
  - *Text and code.* A file whose bytes are text (no NUL, hardly a control
    character; UTF-8, UTF-16 or a single-byte code page charset-normalizer
    finds) is shown read-only with line numbers, search and highlighting by its
    extension or name (CodeMirror 6 and its language data, MIT), and searched by
    its text. No list of extensions decides it: every trade has text kinds no
    list holds (CNC, PLC, device settings, bank exports), the same extension is
    text in one program and binary in another, and an extension names no code
    page. It is never rendered as HTML.
  - *Audio and video the browser plays*: MP4 and MOV (H.264, AAC; HEVC where the
    device decodes it), WebM and Matroska (VP8, VP9, AV1, Opus, Vorbis), MP3,
    M4A, AAC, WAV, Ogg, FLAC, served with byte ranges so it seeks. One the
    browser cannot play says so and is downloaded.
  - *Uploads in chunks.* Cloudflare's 100 MB is per request: every file goes up
    in chunks through one path, a failed chunk is sent again, and the largest
    file is the installation's own setting, refused while the disk lacks room.
    Built: `POST /api/uploads` names the size, each `PUT` brings 32 MB at the
    offset received so far, the last one hashes the file off the shared thread
    and moves it into the tree; an upload untouched for a day is swept.
  - *Images*: BMP and ICO as they are; TIFF, a scan as a rule, becomes a PDF
    with OCR (img2pdf in the `ocr` service), PSD shows the composite it carries
    (Pillow); the original is what downloads.
  - *Archives* (zip and what is a zip, tar and its compressed kinds, gz, bz2,
    xz, zst, lz4, 7z, RAR 4 and 5, ISO, CAB, LHA, XAR): read in the `converter`
    by libarchive (BSD-2) through libarchive-c (CC0), a 7z with a password by
    7-Zip (Debian's `7zip`, LGPL-2.1+ and BSD-3, without the unRAR code), which
    libarchive refuses (tried 2026-10-27 on 3.7.4, content or names encrypted;
    a zip under ZipCrypto or AES it reads). An archive opens as a folder that
    is only read; *Unpack into folder* sends each file on the way an upload
    does; a password is asked for and never kept; the names inside are
    searched; limits on size, count and ratio stop a zip bomb. An encrypted RAR
    is only downloaded: only unRAR reads one, under a licence that is not free.
    A folder or the chosen files download as one ZIP, streamed.
  - *Mail, contacts and calendars in files*: eml and msg (olefile and our own
    reader; extract-msg is GPL) show as a message whose attachments can be
    saved, vcf adds to contacts, ics to the calendar.
  - *Other office formats through the `converter`* (LibreOffice Draw added):
    Visio, Publisher, CorelDRAW and odg into PDF; Pages, Numbers, Keynote,
    WordPerfect and Works into documents; Markdown (markdown-it-py) and HTML
    import as documents; CSV with D22.
  - *Old media and HEIC*, in a `media` service reaching only the backend:
    FFmpeg's LGPL build (Debian's links x264 and x265, GPL) turns AVI, WMV,
    WMA, AMR, 3GP and FLV once into WebM, and libheif with only its libde265
    plugin (pillow-heif carries x265) HEIC into JPEG; the original is kept.
  - *Only downloaded*: PCM without a header, EPS (Ghostscript is AGPL), DWG
    (LibreDWG is GPL, ODA commercial), OneNote, PST, installers. CAD viewers
    stay out while DWG, the common one, has no permitted reader.
  - *Order*: D23-1 text and code, audio and video, uploads in chunks; D23-2
    images and archives; D23-3 mail, contacts and calendars in files, the
    converter's formats, Markdown and HTML; D23-4 the `media` service.
- **D24: a glance at the chosen item beside the folder — closed 2026-10-28**
  (Ivo: "jel bi mogli imati neki preview odabranog file", "slažem se sa
  preporukama"). *Preview* on the folder's bar opens a pane beside the list,
  kept on or off in the browser, and only where there is room for it (768 px
  and wider); a touch still opens the item. One item chosen shows as it reads,
  with its kind, size, change, who made it and who has access; several are
  counted with their size together; none says to choose one.
  - *Images and PDFs* show a picture drawn once per blob, the image made small
    or a PDF's first page, at most 800 px a side as WebP (Pillow, pypdfium2),
    by a drawer in the backend as soon as a file is created and in a sweep.
    The picture is a blob of its own in the tree, like OCR's copy, and a row
    in Postgres refers to it and goes with the bytes: pictures in the database
    would swell every dump and restore. A file the drawer has not come to yet
    is drawn on the spot when asked for. The picture's URL names it, so the
    browser keeps it for good. Measured on the dev data: 40 to 270 ms a file,
    5 to 70 kB for originals of 4 to 15 MB. An SVG shows as itself.
  - *Text files* show their first 64 kB as the text view shows them whole.
  - *Documents* show the first blocks of their first tab as their content was
    last read (the element table): title, headings, paragraphs, a table's first
    rows as they show, images. Read live from Postgres, never a picture that
    every change would leave behind.
  - *Recordings* play in the pane, only their head fetched until played; a
    video's still waits for the `media` service (D23-4).
  - *A document's size and kind* (Ivo: "zašto nemamo size vidljiv za
    dokument", "idemo po preporukama"). A document has no file: its size is
    what its content takes as stored, its Yjs state and its tables' rows as
    Postgres keeps them and the images and PDFs it shows as their files in
    the blob tree, measured whenever the element pass
    reads one of its tabs; search's index, versions and the original it came
    from are not counted. Its kind is what it holds, not where it came from:
    a *presentation* where it keeps slide layouts of its own, a *spreadsheet*
    where its first tab holds tables alone (a chart or notes beside them
    still count as a sheet), a *document* otherwise, each with the icon its
    save menu shows. So a workbook stays a spreadsheet saved as .ponx or
    written in PONISTRA, and a Word file that is one table reads as one.
    The pane names the file an import came from by its extension and size
    (*XLSX file · 14.6 kB*) with its download, closed in a confined folder
    to whoever may not edit there. On the dev data: 79 workbooks of 3 kB to
    7.7 MB (Products: 816 kB as .xlsx, its rows uncompressed in Postgres),
    two slide decks of 21 MB, mostly their pictures.
- **D25: a simple image editor — approved 2026-10-28** (Ivo: "jel bi mogli
  imati neki jednostavni editor slika", "kreni"). Built as notes on a PDF
  are: what is changed lives beside the image in its file's room, the bytes
  never change, and the backend draws the copy with Pillow, so that the
  browser only shows what the copy will be. Our own, not a library:
  Filerobot (MIT) brings a look of its own and edits pixels in the browser,
  where no one else sees them; TUI Image Editor (MIT) is unmaintained since
  2022; Pintura is commercial.
  - *E1, shape and tone*: crop (free, 1:1, 4:3, 16:9) on the picture as it
    shows, turn by 90°, mirror across or down, the longer side made at most
    800 to 2560 px, brightness, contrast and saturation. The room's `edits`
    map holds each on its own key, so two people changing two of them both
    keep theirs, and Ctrl+Z takes back only one's own. The crop is kept in
    the pixels of the image upright (its EXIF turn applied); the tone is
    the browser's brightness, contrast and saturate filters, each clamped
    in turn, which the backend computes the same in sRGB. Once the room is
    quiet for 2 s a pass in the backend draws the copy, a blob of its own
    the file refers to; its glance, its picture in the folder and *Download*
    follow it, a download drawing it on the spot when the pass has not come
    to it yet, and *Download original* gives the bytes as they came. PNG,
    JPEG, WebP and AVIF are edited and kept in their format, ICC profile
    kept and the rest of the metadata, the location among it, left out.
    Built 2026-10-28: *Edit* beside *Share* opens the panel for whoever may
    edit the file; everyone else sees the edits live. The page draws the
    image on a canvas with the same steps as the backend, and the e2e holds
    its pixels to the downloaded copy's within 2 of 255. GIF, BMP, TIFF and
    SVG are shown as before, not edited.
  - *E2, marks*: arrow, rectangle, a line drawn by hand, text and a blurred
    part, in the image's own pixels so that a crop or a turn keeps them in
    place; *Save as a new image* makes a file of the copy, the way to hide
    for good what a blur covers. Built 2026-10-28: the room's `marks` map
    holds each mark under its own id, as the notes on a PDF do, in the pen's
    colours and three widths, in units of a five hundredth of the image's
    longer side; a text is Inter Bold with a white edge and reads across the
    image as it shows. A blur is chosen in whole pixels and drawn before the
    tone, the rest after it, in the order they were made. Without a tool a
    click chooses a mark, which *Remove* or Delete takes away, and Escape
    leaves a tool. The copy is saved beside the file, or among the user's
    own documents where they may not add to its folder; the e2e holds the
    page's canvas to it pixel by pixel.
  - *E3, images in a document*: the same editor on an image a document
    shows; what it draws is a new blob the image refers to, the earlier one
    kept for the versions. Built 2026-10-28: *Edit image…* in the image's
    menu opens the editor over the whole window, its edits and marks held in
    the browser alone, as nobody else edits that copy; *Apply* sends them
    with the image to the document's images, the backend draws them as it
    draws a file's copy and links the new blob beside the old one, and the
    document's image points to it as one step undo takes back. Escape does
    not close the editor once anything is changed; an image of a kind not
    edited says so.
  - HEIC is not read: Pillow needs libheif for it, which is LGPL.
- **D26: an Android app of our own — approved 2026-10-28** (Ivo: "a napravimo
  mi na naš način", "ali ako već radimo aplikaciju za andoid zašto onda nebi
  imala sve potrebno", "ok"). Contacts and the calendar reach an Android phone
  without DAVx⁵, and the whole app comes with them: the web app itself in
  Chrome as a Trusted Web Activity (androidbrowserhelper, Apache 2.0), not an
  interface written again, so that Web Push and the vault's PRF passkeys keep
  working, which a WebView loses. Native code only where the web cannot reach:
  the phone's own contacts and calendar, *Share → PONISTRA*, connecting the
  phone and updating itself. Writing into the user's Google account instead
  was turned down: Google would become a second truth, the company's data
  would leave the installation, and it would come back through the Google
  source as a loop. One app serves every installation: the user gives the
  installation's address at the first start, and each installation serves
  `/.well-known/assetlinks.json` for the app's key, without which Chrome shows
  its address bar above the app. On Android it takes the place of the
  installed web app; an iPhone keeps that and CardDAV/CalDAV.
  - *D26-1, the app, connecting and updating*: built 2026-10-28. `android/`
    (Kotlin, minSdk 28) is built and signed by `android/build.sh` in a
    container of its own, with a keystore that never leaves 210; its version
    counts the commits touching the app, whose launcher icons are vectors
    `scripts/brand.mjs` writes into it (2026-11-13). The release builds it and puts it in the
    frontend's image, which serves `/android/ponistra.apk` and
    `/android/ponistra.json` beside it; the app reads that when it opens,
    after each sync and twice a day, and installs an update it has checked
    (digest, package, version, signer) itself through Android's installer:
    without a word once it is the app's own installer of record, from
    Android 14 only while the app is out of sight; where Android asks, the
    confirmation waits in a notification (2026-11-05).
    *Connect a phone* among the app passwords makes a pairing code, valid ten
    minutes and once: on the phone a link opens the app with it, the download
    beside it, and elsewhere a QR code that the phone's camera opens as
    `/connect`, a page without sign-in. The app claims an app password of
    its own with the code (`/api/device/claim`), so the password never
    travels in a link or a browser's history, signs in with it as a bearer
    token to the views that take one (`/api/device`: JSON over the REST
    API), names it after the phone and keeps it as an Android account,
    which removing signs out.
  - *D26-2, contacts*: built 2026-10-30. The phone's Contacts app holds the
    user's PONISTRA address book both ways through that account: a sync
    adapter of the account, with the edit schema that lets the Contacts app
    (Samsung's, Google's) write into it and offer it for a new contact. It
    reads `/api/device/contacts?since=<revision>` (every contact, or those
    changed since and the hrefs deleted since; 410 after a restore, and the
    phone reads the whole book again) and writes
    `/api/device/contacts/<href>` at the revision it read, under an href of
    its own choosing for a new one, kept as a CardDAV phone's card is
    (`cards.saved`). PONISTRA holds the truth: a write at a revision that
    changed since is refused (412) and the phone takes PONISTRA's. The phone
    keeps the rows it does not know (messengers, relations, other dates) and
    the rows that stayed the same, so a default number stays so; the photo
    goes up only when the phone's changed. It syncs as the phone connects,
    as the app opens, after each change on the phone and every 15 minutes;
    without access to the contacts it says so in a notification that opens
    the app's settings. Once an account syncs, the app asks Android once to
    keep it out of battery optimisation: an optimised app left in the
    background is frozen with its network closed (Samsung's freezer), and as
    Android starts no sync without network, none ran from 11:22 to 15:36 on
    2026-11-05 until the app was opened. A star taken off in PONISTRA comes
    off the person, as Android stars every account's card of them together.
    The DAVx⁵ advice has left the app passwords.
  - *D26-3, calendar*: built 2026-10-30. The phone's Calendar app holds each
    of the user's calendars through the same account: their own both ways, an
    organisation's read only, as over CalDAV, each with the address the user
    has in it, so the Calendar app knows which attendee they are. A series
    comes as CalDAV gives it (`ical.told`), in JSON: its master, the
    occurrences changed on their own, and each occurrence its way with days
    off moves, which comes back as that way alone (`ical.settled`). The phone
    lists `/api/device/calendars` (each with the revision it reached), reads
    `/api/device/calendars/<id>?since=<revision>` as the contacts, and writes
    `/api/device/calendars/<id>/<href>` at the revision it read, 412 when it
    changed since. What only PONISTRA holds (the conference, the lines it keeps
    unshown, the sequence) stays; who is asked to a meeting stays as its
    organizer set it unless the user organizes it. A meeting the user
    organizes and changes on the phone reaches its attendees as a change on
    the web does; their answer to one they are asked to reaches whoever asked,
    before the series is written, so an answer not taken leaves it as it was.
    The colour PONISTRA gives a calendar is the phone's until the user picks
    another there. A phone connected before D26-3 is asked for the calendar
    as the app next opens.
  - *D26-4, sharing*: what another app shares (files, a link, text) goes to
    PONISTRA. *Built 2026-10-30* (Ivo: "ne nudi mi scriptor kad želim share
    with iz galerije"). The web app's manifest names a share target, `/share`,
    posted as a form (title, text, url, files); the service worker keeps what
    comes in the browser's own store and hands it to the page there, so nothing
    reaches the server before the user says where it goes. The phone app takes
    SEND and SEND_MULTIPLE of any type and has Chrome post them to the
    installation's target, of the files only those the sharing app let it read;
    the library posts only to a target named in full in the app's manifest, and
    the installation's address is known only at run time, so the app gives the
    target as it launches (`Sharing.kt`). The page shows what came, pictures as
    thumbnails, and offers *Save to folder* (any folder the user may add to,
    through the uploads the tree already has) and *Send by email* (a new message
    with the title as its subject, the text and link as its body and the files
    attached). A link or text alone is not saved as a file. *To a conversation*
    (S2-3d) leaves text and files in the composer of the one chosen. Only the
    share target wakes the service worker: every other request goes to the
    network past it (static routing).
- **D27: notes — approved 2026-11-01, built 2026-11-02** (Ivo: "mislim samo kreiranje nekog
  notesa da ostane zapisano - kao samostalna datoteka", "trebale bi biti
  privatne. uvijek se mogu obraditi i objaviti kasnije kao zajedničke kao neki
  dokument"). A note is something written down at once so that it stays. It is
  a document like any other, not a kind of its own with an editor of its own,
  so it has what a document has: live editing on every device, versions,
  search, rights, export and actions. Only how it is made and shown differs.
  - *Private.* Notes lie in the user's own *Notes* folder in My documents, made
    with the first note. Nobody else reads one until the user shares it or
    moves it into a shared or company folder, where it is a document with
    nothing converted.
  - *Made in one move.* *New note* on the notes page, in the command box and
    by Alt+N on any page opens a new document there, with no folder and no
    name to choose; its name follows its first line until the user names it
    (`follows_text`, set as the element table reads its first tab, and the
    open document hears of it as of its tabs).
  - *Shown as notes.* Notes sits in the Documents column under Shared
    (Ivo, 2026-11-02: "zašto bilješke ne bi bile pod dokumenti"), not as a
    module of its own, and the notes folder is left out of the folder rows and
    the My documents list (`/notes`, where the folder itself leads too): cards with the name and the start of
    the text after it, the favourites first (D48), then the latest changed.
  - *From elsewhere.* The share page (D26-4) saves a link or text as a note,
    which it could not save before; the installed app and the Android app offer
    *New note* as a launcher shortcut (`/notes?new`). Dictation into a note comes with speech to text (D28).
- **D28: speech to text — approved 2026-11-02** (Ivo: "a nisam siguran da se
  isplati lokalno. možda da ipak upotrijebimo cloud llm za ove stvari", "ok,
  slažem se"). Dictation, spoken commands and a meeting's transcript (S2-6) go
  through OpenAI's `gpt-transcribe` with the installation's own key, off until
  the administrator turns it on and under the user's consent, as Claude is
  (D14); audio leaves only then. Claude takes no audio, so the language work
  on the text (a spoken command to an action, a question to a query, minutes)
  stays with Claude. Transcription is one replaceable layer behind one
  interface. Measured 2026-11-01 on FLEURS hr (150 sentences, 25 minutes):
  `gpt-transcribe` 11.0 % of words wrong, Whisper large-v3-turbo on four CPU
  cores 13.2 % but 1.2× the audio's length to run, too slow for dictation on
  a small firm's server, Parakeet v3 20.0 % and not under a licence allowed
  here, `gpt-4o-transcribe` 23.5 %, `gpt-4o-mini-transcribe` writes Serbian.
  A spoken command is matched against the actions' labels in code first, as
  the command box matches typed ones; only what matches none goes to Claude.
  A question over a table never becomes SQL from a model: Claude answers
  with a structured filter, grouping or total, which D22's compiler turns
  into SQL inside the user's rights and the user sees as an editable filter.
  No local model still holds (2026-10-20).
  - *Built 2026-11-02: the microphone.* A microphone beside the search box on
    every page (Ivo: "mora biti lako dostupni botun koji može pokretati i
    druge zadatke"), Alt+M and the launcher shortcut `/?voice`. The
    administrator turns speech on with the OpenAI key on the AI page, kept
    sealed as Anthropic's is; the user consents once. It records up to ten
    minutes, sends the audio to `/api/speech` (at most 25 MB, never kept)
    and matches the text against the search box's commands: one said by its
    name runs; otherwise the text is shown, editable, with the commands that
    hold its words and *Save as a note*.
  - *Built 2026-11-02: Claude reads what was said.* While the installation's
    AI is on, text that names no command and is under 2,000 characters goes
    to Claude (Haiku, `speech.understand`, under the same consent, which
    names Anthropic too) through one choice of three tools: an event
    (summary, day, time, end, place), a task (text, due) or a note. The
    dialog shows the proposal; an event opens in the calendar's own event
    dialog, a task in the task dialog, filled in and saved there by the
    user, so nothing is written without them.
  - *Built 2026-11-02: basic voice commands.* The commands said by name
    include *Otvori: <place>* for every module, notes, tasks and the trash,
    *Nova poruka* and *Novi dokument*. Claude reads four more intents: open
    a place (the calendar on a named day), search (the search box's filters,
    words in their base form, so "odgovori Evi na mail" finds Eva's
    messages to answer), a new message (recipients resolved through the mail
    people, body without greeting or closing as the signature follows,
    opened in Compose to check and send) and a new document under the title
    said, opened in the name dialog. Whisper-family models write Croatian in
    Serbian Cyrillic at times; text whose Cyrillic is all in the Serbian
    alphabet is transliterated to Latin, and no language is sent. The
    speech to text is told beforehand the names the user uses (OpenAI's
    `prompt`): the people they write to most and the names in the titles of
    their folders and documents (a capital inside a word, a capitalised word
    after the first, abbreviations), the most frequent first, at most 800
    characters (Ivo: "ne prepoznaje mi TaskStreamer"; with it, TaskStreamer,
    StoreMaster and RetailUp come back as written).
  - *Built 2026-11-02: a person asked about.* A question about someone
    ("kad je rođendan Bore Vrančića", a phone number, an address) is a fifth
    intent: Claude gives the name in its base form, the contacts are matched
    by trigram likeness on the folded name, so a misheard "Dino Vrančec"
    still finds Dino Vrančić; one clear match opens the contact, several
    are offered to choose from, none is said.
- **D29: the licence and the name — approved 2026-11-02** (Ivo: "da bude free
  za osobnu upotrebu a paid za business", "ajde još jednom razlozi zašto ne bi
  išli kao dida i baba", "ok, krenimo sa svim"). No OSI licence can tell a
  person from a firm, so AGPL-3.0 goes. The licence is PolyForm Noncommercial
  1.0.0, as DIDA, BABA and OPUS: free for personal and non-commercial use, a
  firm's use under a separate commercial licence sold on request. Nothing in
  the app counts users or checks a key; a Business Source License with a
  threshold and a licence key was weighed and dropped as work without need.
  - *The name.* SCRIPTOR is taken for our goods in the EU (TMview,
    2026-11-02): EUTM 009522343 of Scriptor Technology A/S (Denmark; class 9
    covers software for the electronic management and handling of documents
    and for document workflow, beside 35, 37 and 42), and national marks in
    Spain (M2557062, M2550849, class 9) and Portugal (050000361665, class 42).
    The product becomes **Ponistra**, Dalmatian for window (from Latin
    *fenestra*): TMview holds no mark containing it in any office or class
    (2026-11-02); ponistra.com and .hr belong to a maker of PVC windows in
    Biorine, other goods. Croatian declines it as a feminine noun (Ponistra,
    Ponistre, Ponistri, Ponistru, Ponistrom). The three sheets stay; the
    wordmark, drawn anew from the board's letters, replaced the old one on
    Ivo's approval ahead of the rename (2026-11-02).
  - *No product domain.* An installation reaches only the image registry and
    its own domain, so the product needs none; its public face is the
    repository's README, as DIDA's and BABA's.
  - *Trademark.* Filed at the EUIPO (classes 9 and 42) when the first firm
    asks for a commercial licence, through whatever legal form sells it then.
  - *The rename* is two moves. The tree (2026-11-02): every text a user or
    an administrator reads, in both languages, the Android app's label and id
    (`biz.boskovic.ponistra`, its link scheme `ponistra://`), documents' and
    exports' metadata, DAV collections, passkeys, invitations, the code's
    names and Ponistra's own file, `.ponx` (`application/vnd.ponistra.document+zip`;
    a `.scrx` is no longer read), the release images (`ghcr.io/bacinac/ponistra-*`),
    the install command (`ponistra`), the APK's shelf (`/android/ponistra.apk`)
    and the LiveKit key. The switch (2026-11-04): the dev directory
    (`/mnt/docker/ponistra`), the compose project and its containers, network,
    volumes and dev images, the settings' prefix (`PONISTRA_*`), the database's
    role and name, the ActiveSync device type and the public URL
    of our production. Kept for good, as
    stored data depends on them: the labels that seal secrets (`core/sealed.py`)
    and the vault's keys, and the backup host the snapshots are kept under.
- **D30: table designs — approved 2026-11-02** (Ivo: "Izgled tablice u modelu",
  a bigger job of several days). A table's look belongs to the table, not to
  paint on its cells. The header, the totals, the bands of rows and columns,
  the first and last column and the corners each have a look, and the table
  says which of them are on. The look follows the table as rows come and go
  and as it is sorted. Word, Excel and PowerPoint all keep a table this way,
  as a table style with its switches, so a table comes in from each with its
  style and goes back out as one. Before D30 an import painted nothing of a
  table style: Word's and PowerPoint's were counted as `lost.tableStyles`,
  and Excel's tables were dropped without a word.
  - *The design* is one of `designs`, an attribute of the table
    (`$defs.design` in schema.json); a table without one is plain. Word's and
    PowerPoint's tables have one. A sheet has one for each of its Excel tables,
    each over its range (`area`), and where its cells keep lines of their own,
    first Excel's rules over the whole sheet, drawing nothing, for those lines
    to meet as Excel's do. A design's keys:
    - `parts`: `table`, `rowBand1`, `rowBand2`, `columnBand1`, `columnBand2`,
      `firstColumn`, `lastColumn`, `header`, `totals`, `topLeft`, `topRight`,
      `bottomLeft`, `bottomRight`. Each part may set:
      - a fill;
      - marks over its text: bold, italic, underline, strike, colour, caps,
        small caps, size, font;
      - its paragraphs' alignment and its cells' vertical alignment;
      - edges: `top`, `bottom`, `left` and `right` round the part's region,
        `insideH` and `insideV` within it. Each edge is a line (`color`,
        `width` in points, `line`: the line styles of ECMA-376 §17.18.2, which
        Excel's and PowerPoint's map onto) or `none`, which takes away a line
        that a part beneath drew.
    - `on`: the switches, `header`, `totals`, `firstColumn`, `lastColumn`,
      `rowBands` and `columnBands`.
    - `bands`: the rows and columns in a band; a style that names no size has
      none in Word, so its bands never show.
    - `lines`: Word's table-level borders, under every part's own.
    - `background` and `shadow`: PowerPoint's, a fill or gradient under the
      cells and a shadow under the table, from a themed style or from the
      table's own `a:tblPr`.
    - `spacing`: Word's cells set apart, by twice the spacing. Each cell then
      draws its own four sides (its own line, then the parts', then the
      table's `insideH` and `insideV`, on the table's edge too), no edge meets
      another, the table's outer `lines` draw only the frame round them all
      and its shading shows between them.
    - `name`: the style it came from, which an export names.
    - `rules`: see the next point.
  - *Rules* (`word`, `excel` or `powerpoint`). The programs agree on the
    parts but not on how the parts meet. The design keeps the program it came
    from, and the rules below are each program's as measured against it:
    - Word:
      - A later part wins in a cell, in this order: table, row bands, column
        bands, last column, first column, header and totals, corners.
      - The header, the totals, the first and the last column take their row
        or column out of the bands only where the style defines them, or
        defines a corner that holds them while both of that corner's switches
        are on. A part counts as defined once its element holds anything,
        even only paragraph settings; an empty one does not. Otherwise the
        bands start at the first row or column and run into the last.
      - A corner applies where both its row and its column are on.
      - A band's region is its nominal size: where the table's end or a row or
        column taken out of the bands cuts a band short, its last side takes
        the band's inside line, not its bottom or right.
      - A column band's `insideV` draws nothing while the style's row bands
        are under two rows; it falls through to the parts and lines beneath.
      - The style's `wholeTable` part and its base `tcBorders` are not drawn.
      - A cell's side takes the first line it finds: the cell's own, then
        the parts' (a later part's, a `none` taking a line away), then the
        table's `lines`.
      - A shared edge, whichever of those each side's line came from:
        1. A line beats no line.
        2. dotted is the weakest line and dashed the next, whatever their
           width.
        3. Then the heavier line wins. Its weight is the width in eighths of
           a point × the line's code in Word's binary format, not ECMA's
           number: single 1, thick 2, double 3, dotDash 8, dotDotDash 9,
           triple 10, the thin-thick lines 11 to 19, wave 20, doubleWave 21,
           dashSmallGap 22, dashDotStroked 23, the 3-D lines 24 to 27.
        4. At equal weight the higher code wins.
        5. Then the darker colour (R+B+2G, then B+2G, then G).
    - Excel:
      - The order is table, column bands, row bands, last column, first
        column, header and totals, corners.
      - Bands lie only in the data rows. Column bands start at the first column
        and run over the first and last.
      - A corner needs its column's switch too.
      - A part's region is its contiguous cells.
      - A shared edge: a line beats none, then the stronger line style (hair <
        dashDotDot < dashDot < dotted < dashed < thin < mediumDashDotDot <
        slantDashDot < mediumDashDot < mediumDashed < medium < thick < double),
        then the darker colour (2R+5G+B, then the bluer, then the less green).
    - PowerPoint:
      - Word's order, with the corners where CT_TableStyle puts them (lastRow,
        seCell, swCell, firstRow, neCell, nwCell).
      - A part applies whenever it is switched on.
      - A shared edge goes to the later part in that order, whatever the
        width: the header's bottom over the totals' top in a table of two rows,
        the only clash PowerPoint's own styles have.
      - PowerPoint draws only its own 74 styles, by their GUID, and ignores
        what a file defines under it. A GUID it does not know, a custom
        style included, is drawn as No Style, Table Grid, and so is a table
        without one.
      - The table's own fill and effect in `a:tblPr` replace the style's
        background and shadow, under any style. A shadow is cast only from
        what is filled: a table without a fill casts none, its lines none
        either.
  - *Under the cell's own look.* A cell's own fill and marks, and a row's or a
    column's look (`look`), win over the design, as in each program.
  - *A cell's own edges* (`edges` of a cell: `top`, `bottom`, `left`, `right`,
    each a line or `none`) sit over the design. Every program keeps them, and
    no import read them before D30. Where they meet:
    - Word: a cell's own line, or its `none`, wins in its cell; a table's own
      `tblBorders` replace the style's, side by side, as the design's
      `lines`. Every shared edge is then settled by the steps above, an own
      line against a part's or a table's like any other.
    - Excel: a cell's own line wins in its cell over the design, even a
      weaker one. Two cells' lines on one edge meet by the ranking above, then
      the darker colour; one stored side shows for both cells.
    - PowerPoint: a cell's own line, or its `none`, wins in its cell. On an
      inner edge only the upper cell's bottom and the left cell's right
      count; the lower cell's top and the right cell's left are ignored, even
      alone. On the table's outer edges each cell's own line counts.
  - *Replaces `borders`.* The attribute `borders` (`all`/`none`) goes:
    - a table without a design has no lines (Pages shows its guides while it is
      edited);
    - a new table takes the design Mreža (every edge single, ½ pt, Word's rules);
    - stored tables are migrated, `all` to Mreža and `none` to no design.
  - *Colours.* A part's colours are palette names or the file's own #rrggbb,
    as everywhere (`$defs.color`). A fill may carry an alpha (#rrggbbaa),
    since PowerPoint's light styles lay their bands over the table's
    background. A theme's colour is resolved on import, each program its own
    way:
    - Word: the theme with tint and shade;
    - Excel: the tint in Windows HLS, exact to Excel's rounding, replacing the
      approximation `ironcalc.hex_with_tint_to_rgb` gave;
    - PowerPoint: tint and shade in linear RGB.
  - *Resolving.* One rule set, `schema/tables.json`, holds the parts' orders,
    the bands' reach, the line weights and the rankings of each program. Two
    readers use it:
    - the editor's resolver (`editor/design.ts`), which gives a cell its parts,
      fill, marks and four edges once shared edges are settled. Every view
      draws from it: the canvas, the cells in the text, the paper and slides.
    - the backend's twin (`apps/content/designs.py`), used where an export
      writes the look into the cells and by the tests that hold imports to the
      etalons. `schema/tables.cases.json` holds its results, which the
      editor's resolver must give alike.

    Designs over areas lie one over another, a later one over an earlier. An
    edge two cells under one design share is settled by its rules; one between
    two designs, or beside a cell under none, by the rules of the table's
    first design, Word's in a table without one (both readers, `laid` and
    `TableDesign`).
  - *Import.* What a design cannot hold (a pattern fill, a part's own cell
    margins) is counted under `lost.tableStyles`.
    - Word: the table's style (styles.xml carries every style the document
      uses, the built-in ones included) and `tblLook`. A part's `tcBorders` is
      kept apart from the style's `tblBorders`.
    - Excel: a table's style (`tableStyleInfo`) over the table's range. A
      built-in one comes from ECMA-376's `presetTableStyles.xml`, a custom one
      from styles.xml's `tableStyles` and `dxfs`, with the table's switches.
    - PowerPoint: `tableStyleId`, always from the 74 built-in styles, since
      PowerPoint draws those and nothing a file defines; any other GUID, or
      none, comes in as Table Grid, an unknown one counted. The styles are
      our own description (`imports/tableStyles.json`): 14 families, each a
      plain member and its accent variants as PowerPoint derives them,
      measured against PowerPoint's drawing of all 74. A theme's line
      (`lnRef`) takes its width from the deck's theme. The switches, the
      table's own fill and its shadow come from `a:tblPr`; a shadow over a
      table only partly filled is counted and left out, as the design casts
      from its whole area.
    - A cell's own edges: Word's `tcBorders` in a cell, Excel's cell
      borders, PowerPoint's `lnL`, `lnR`, `lnT` and `lnB`.
  - *Export.*
    - docx: a table style of the design's name, with a `tblStylePr` per part
      and `tblLook`.
    - pptx: a design that PowerPoint draws as one of its own styles, in the
      deck's theme, goes out as that GUID with the switches. Any other is
      written into the cells (fills, the lines `lnL` to `lnB`, the text's
      marks) under No Style, No Grid, its background and shadow into
      `a:tblPr`, since PowerPoint would draw a custom style as Table Grid.
      `tableStyles.xml` stays empty.
    - xlsx: an Excel table over the sheet with a custom table style (`dxfs`)
      and the design's switches as the table's; with merged cells, the look
      written into the cells.
  - *Editing.* The table's menu holds Izgled tablice:
    - the designs to choose from, our palette's from light to dark plus the
      ones the document brought in;
    - the six switches.

    A new row or column takes its look from the design. The actions
    (`table.design`, `table.switch`) are in the registry. The Totals action
    turns the totals switch on when it writes its row.
  - *Measured* on Ivo's laptop, through COM without saving (`etalons/tables`,
    never committed). Each result is the number of differences between our
    rules and the program:
    - Word: 247 styles with random switches and sizes, 825 tables, 46 248
      edges, 0 differences; probes for each shared-edge step, and every pair
      of a style's part, a style's table line, a table's own line and a
      cell's own line on one edge, read from a file, 0. Cells set apart and
      the bands' reach measured from the page's picture (EMF), each line by
      its colour: 40 tables of every spacing, then 40 of random band sizes,
      parts and switches, 0. The spaced built-ins Table Web 1 to 3, where COM
      reports the frame on an outer cell's side, from the picture: 600 cell
      sides and 144 frame sides, 0. Acceptance: 60 fresh tables each set apart
      (4 564 cell sides, 300 frame sides) and close (2 806 edges), with
      empty parts and parts holding only what the import does not read, 0.
    - Excel: 240 tables and 3 832 cells, plus probes for reach, order, bands,
      regions, clashes and the line ranking, 0; the colour of two lines of one
      kind on one edge over 1 500 pairs, 0. Acceptance: 39 fresh tables of
      built-in and own styles on 10 sheets with cells' own lines, 1 981 cells
      and 9 905 fills and sides, 0.
    - PowerPoint: all 74 styles, fills over 3 961 cells and 15 844 edges, 0;
      the header and totals clash in all 28 tables that have it, and a cell's
      own lines over the built-in styles, drawn and read alike. Probes for the
      table's own fill and shadow under No Style, a built-in and Table Grid:
      replaced, cast only from fills, alpha and gradient angle kept.
      Acceptance: 300 fresh tables, 3 742 cells and 14 968 edges, 0, both as
      written and as PowerPoint saved them.

    PowerPoint is measured from the slide's picture wherever COM can differ
    from it: COM reports a custom style as the file defines it while
    PowerPoint draws Table Grid, and it reports a theme's line black in a file
    PowerPoint did not make. COM does not report PowerPoint's text, its themed
    background or its shadow either. Word's tables of close cells are measured
    through COM, which leaves some sides undefined (`wdUndefined`) and does
    not hold for cells set apart; those, and Word's acceptance, are read from
    the page's picture (`Page.EnhMetaFileBits`): its PDF export hangs under
    COM, and its pictures of a range leave a style's parts out.
    Acceptance is a fresh random sample per program, with 0 differences.
- **D31: links (bookmarks) — approved and built 2026-11-03** (Ivo: "a što
  misliš da dodamo bookmarks stranicu u ponistra, nešto što imamo u
  homepage", "ok, nastavimo"; for the page: "d, tako bi da ih dodaš"; for its
  own place: "a zašto su pod my documents… dodao bih i group… unio bih sve
  linkove koje imam na homepage, sa ikonicama"). A
  fourth kind of item in the tree, the **link** (Poveznica): a web address in a
  folder, so
  folders, sharing, the organisation's folders, search, the trash, the glance
  beside the folder and the access log hold links as they hold documents. An
  organisation's shared folder of links is its launcher; Homepage's widgets
  (status, counters) stay out.
  - *The link.* An address of the web (`http`/`https`; one typed without a
    scheme takes `https://`), a name and what the page says it is. Unnamed,
    it bears its site's name until its page is read, and then the page's
    title, until the user names it. It opens in a tab of its own, from the
    folder, the search box (Enter) and every list of items; the Today page's
    recent documents leave links out, as a link has its page. Shown away from
    its folder, an item in a place of the user's own begins its path there
    ("Poveznice › Posao", "Bilješke"), not in My documents.
  - *Reading the page.* A background reader (`documents/links.py`) fetches
    the page once through the public fetcher (`core/fetch.py`, which refuses
    addresses behind the server) and keeps its title, its description and its
    icon drawn as a 64 px PNG (an SVG drawn by the printer); a changed address
    is read anew. A name, description or icon the link was given stays. Of a
    page that cannot be read, behind a sign-in say, only the site's
    `/favicon.ico` is kept. Where the site gives no icon, the icon of the
    site a level up is taken, as a company's mail host
    (`wm.<company>.com`) bears the company's; never for an address alone. A
    site that refuses a server outright (a bot check) keeps no icon: the
    page shows its letter until the user gives one.
  - *Coming in.* "Spremi u mapu" on a page shared from the phone or another
    app makes a link in the chosen folder. A browser's exported bookmarks
    (`bookmarks.html`, the Netscape format every browser writes) come in
    through "Učitaj datoteke…" as a folder of links in their folders, with
    the icons the export carries.
  - *Search* finds a link by its name, by what its page says and by its
    address; `vrsta:poveznica` lists links alone.
  - *The page of links* (`/links`, "Poveznice" beside Notes in the folders'
    column). Each user's links have a place of their own, like Notes: a
    top-level folder flagged `links`, made the first time something goes into
    it, never moved and hidden from My documents; its folders are the
    **groups** the page shows by name, nested ones as "Posao › Poslužitelji".
    Links at its top come first without a heading, then each group (an empty
    one too, a quiet frame saying so). Below them the links of the
    organisation's folders and of what others share, grouped by the folder
    along the user's path, its heading opening that folder.
    A tile is the icon in a frame of its own (none read, the site's first
    letter in a colour of its own), the name and what the page says; a click
    opens the page in a new tab (from the installed app, a tab of the
    browser's window, each next link beside it). "Novo" makes a link, a group
    or loads links. Nothing else stands on the page: a long press (or a right
    click) on a group's heading offers a new link in it, renaming, its
    columns (as many as fit, or one to six, fewer where the page is too
    narrow) and the trash with its links; on an editable folder of others',
    a new link in it. A long press on a tile chooses it, as items are chosen
    everywhere (`useChoice`), and the bar over the page edits one, moves
    the chosen to another group or to the trash; a right click offers the
    same for one tile.
  - *Laid out by the user.* With a mouse, groups and tiles are dragged where
    they should stand, the tiles chosen together, into another group too
    (`/api/nodes/move` with `before`; `Node.position` among siblings, those
    never laid out following by name). A new link, a new group and what is
    moved in without a place stand last; loading lays out what it makes in
    the order of the file. An empty group's frame takes a drop, and while a
    link is dragged and none stands outside a group, a frame below the groups
    takes it out of them; nothing appears above the dragged tile when a
    drag starts, so nothing under the pointer moves.
  - *An icon the user gives.* The link's dialog shows its icon, takes an
    image chosen from the computer, a Homepage icon name (`proxmox.png`,
    `mdi-router-#00ff00`, `si-github`) or an image's address, and removes
    one, the reader then reading the site's icon again; an image file
    dropped on a tile becomes its icon. A given icon is drawn as a read one,
    from an image of up to 8 MiB and 25 megapixels.
  - *Loading links* ("Učitaj poveznice…", the job `links`) takes several files
    at once into the place, beside what it holds: a group of the same name is
    joined and an address already in it is not made again, so loading again
    makes nothing twice. A browser's `bookmarks.html`; Homepage's
    (gethomepage.dev) `services.yaml` and `bookmarks.yaml`, each group a
    group, a group inside a group nested, a service's or bookmark's name,
    address, description and icon read, its widget and the credentials in it
    never; and the image files the YAML names as `/icons/…`. Homepage's icon
    names are found where Homepage finds them (dashboard-icons, selfh.st,
    Material Design and Simple Icons, the last two drawn in the colour given
    or a neutral grey).
  - *Said* (Ivo: "jel možemo imati neke glasovne akcije po njima"). The
    microphone opens a link of the page by name: "Otvori Github" said word
    for word without the model, otherwise the model reads a link meant
    ("otvori Grafanu", "idi na Proxmox") and the page's links whose name holds
    one like it (`word_similarity` ≥ 0.6) are taken, the likest alone where
    it clearly leads. One opens in a tab of its own; several, or one the
    browser will not open this long after the click, are offered in
    "Izgovoreno" to be clicked; none goes to the search for the name. "Pokaži
    mi poveznice" opens the page.
  - *Added by an agent* (D18, 2026-11-05; Ivo: "dodaj add link"). `add_link` puts a link on
    the page, in a group it names and makes where there is none; an address already in that
    place stays as the user left it. claude.ai refuses to be framed, so a link to an artifact
    there opens in a tab of its own.
- **D32: the installed app on a computer — approved and built 2026-11-03** (Ivo:
  "a što misliš da ponistru vrtimo u našem custom lite browseru", then "ok,
  dopiši ova 4 i kreni u implementaciju"). No browser or desktop app of our own:
  the app installed from Edge or Chrome is that window already, its engine
  patched by its makers every week, Web Push and the vault's PRF passkeys
  working, which an Electron shell loses as D26's WebView would have. What a
  desktop app would add comes through the installed app's manifest
  (`vite.config.ts`).
  - *Files.* `file_handlers` offers Ponistra in the computer's "Open with" for
    the kinds it imports (`importable.ts`) and PDF. A file opened so is placed
    among the user's documents as an upload is; a single file then opens. The
    file on the disk stays as it was: nothing is written back into it, as a
    faithful round trip of Office files is out of scope and an export over the
    original would drop what the export does not carry. "Spremi kao" saves a
    copy.
  - *Mail links.* `protocol_handlers` takes `mailto:` (RFC 6068: recipients,
    copies, blind copies, subject, text) into a new message from the default
    account, once the user lets the app be the computer's mail program.
  - *A count on the icon.* What the rail counts, new mail in the inboxes and
    the others' messages in the conversations, stands on the app's icon
    (Badging API). While no window of the app is open, every notice pushed
    carries the count the backend makes (`push.notices.UNREAD`, which mail and
    chat register) and the service worker puts it there.
  - *One window.* `launch_handler` is `focus-existing`: an opened file, a mail
    link or a shortcut goes into the window last used instead of a new one,
    and starting the app brings that window forward as it was. A launch that
    lands in a meeting's or a presenter's window is handed to the main window
    (a Web Lock names it, a BroadcastChannel carries the files); while no main
    window is open, that window says so and opens one. A share target launch
    stays as it was, as Chromium ignores the launch handler for it.
    An address the server answers itself, such as an agent's sign-in, is left
    to the server, as the app has no page for it.
- **D33: confirming who is at the browser — approved and built 2026-11-03** (Ivo:
  "a hoćemo li za vault dodadi 2fa ili možda i za neke ostale dijelove", then
  "slažem se - nastavi"). No second factor on the vault: its key never leaves
  the browser, and the vault password or a passkey's PRF already is a secret the
  server never sees, so a code the server checks would guard only the handing
  out of ciphertext. What an open session (a stolen cookie, a laptop left
  unlocked) could do alone is the gap, and the sign-in itself.
  - *Confirmation.* A view names the methods that wait for a recent one
    (`@api(..., confirmed=...)`); older than ten minutes, it answers 403
    `confirm_required`. Every sign-in confirms, and so does `/api/auth/confirm`:
    a passkey of the user's own, or the password where the policy still lets
    them sign in with one (not a covered user who has a passkey). The frontend's
    request layer opens one dialog for every request waiting on it and sends
    them again once the user has confirmed; closed, they fail as refused.
    The owner's actions on Projects (the terminal, opening the code workspace,
    push and restart) take a confirmation of the last eight hours instead
    (`confirmed_for`, KR35, Ivo 12.11.2026: asked every ten minutes it stood in
    the way of a working day there). A session saves only the keys its request
    changed, over its row locked as it is by then: saving the whole of it, a
    request begun before a confirmation and marking the browser seen on its way
    out took that confirmation back.
    Confirmed: a new or removed passkey, an app password, pairing a phone, an
    outside agent's consent (D18), a new password (no longer the current one
    beside it); creating and changing users, the sign-in policy, the vault's
    recovery through the company and a user's recovery, the off-site copy and
    its emergency kit; the vault's new password or recovery code, its passkey
    unlocks, its export and giving it up.
  - *Passkeys as the second factor.* A passkey is two factors already (the
    device and its PIN or biometrics) and a fake page cannot take it, which a
    one-time code from an app can be, so there is no TOTP. A new installation's
    policy asks everyone for a passkey: its first administrator adds one right
    after setting it up, and each user at their first sign-in with the password
    an administrator handed them. A lost phone: an administrator sets a new
    password, which takes the passkeys the policy would refuse it for, and the
    user adds a passkey again. A lone administrator does the same on the server:
    `ponistra access <email>` prints the new password and ends the sessions.
    The sign-in page also offers the device's passkeys under the email field,
    beside its button for a browser without that list or a key on another device.
    Each user can pick in the settings which method the page leads with (none by
    default, then it offers both equally), the other a click away; the account
    keeps the choice and the browser a copy for the page, and it decides what is
    shown, never what is allowed, which stays with the policy.
  - *Notices.* A sign-in, a new passkey and a new app password (a phone's
    included, once it claims it) are pushed to the user's browsers (Web Push,
    S2-4), opening where they can be seen and taken back: Devices, Passkeys, App
    passwords.
- **D34: a code workspace — approved 2026-11-03** (Ivo: "a razmišljam da dodam
  editor tipa vs code u ponistru", then "slažem se sa svim. nastavi"). The way Ivo
  builds software, talking to an agent that writes the code, needs a page with the
  folders, the files the agent writes and the agent beside them. code-server (MIT),
  VS Code in the browser, is that page. The agent is its maker's own extension
  (Claude Code), which the owner installs from Open VSX and signs in to with their
  own account: Anthropic's terms let no third party offer claude.ai's sign-in or
  hold its tokens, and PONISTRA touches neither.
  - *One user.* A code-server is one person's: one home, one agent account, one
    terminal. The workspace is the installation's owner's alone, the e-mail named at
    install (`PONISTRA_WORKSPACE`); nobody else sees it, administrators included. A
    workspace for each user would need PONISTRA to start containers, which is root
    on the host.
  - *The door.* `/code/` goes through PONISTRA's sign-in: Caddy, and Vite on the dev
    host, ask the backend's door before every request and WebSocket. Opening it from
    the rail waits on a recent confirmation (D33) and then holds for seven days in
    that browser's session; signing out ends it.
  - *A window away.* A window whose connection dropped keeps its extension host, agents
    and terminals for three days, whatever other windows do; closing the tab ends them
    at once.
  - *Copying from the Claude panel.* A drag that brings the panel focus keeps its
    selection, and a selection survives the window regaining focus: the extension
    would move the cursor to its prompt at that moment and Ctrl+C would silently leave
    the old clipboard. Right-clicking inline code selects it, so Copy has something to
    copy. The image patches the page hosting webviews (`workspace/webview.mjs`), and
    the build fails if that page changes.
  - *Here or elsewhere.* At install the owner chooses where it runs: here, as the
    `workspace` service behind PONISTRA's door, or elsewhere, on a machine of
    their own at an https:// address (`PONISTRA_WORKSPACE_URL`) behind a door of
    its own, such as Cloudflare Access or a VPN. Code in the rail then opens that
    address in a tab; the installation runs, keeps and guards none of it. The same
    image serves there, run with the installation's public address. Its scheme is
    the system's, as PONISTRA's choice stays in PONISTRA's origin.
  - *Docker.* For a workspace here the owner chooses whether the agent may run
    Docker on the host (`compose.docker.yaml`, the socket mounted in). That is root
    on the host, and the question says so. Without it the workspace edits files and
    runs git and the agent, and reaches nothing else of the host.
  - *The agent and PONISTRA.* On its first start the workspace lists PONISTRA's own
    MCP server (D18) in the agent's configuration, at the installation's public
    address (`PONISTRA_PUBLIC_URL`, which install writes). Once the owner consents
    there, the agent reads and writes their documents, mail and calendar as any
    outside agent does; PONISTRA holds none of its tokens. The browser that
    consents is not where the agent runs, so the agent's panel takes the address
    the consent lands on.
  - *The image* (`workspace/`): Debian trixie with code-server's release, three of
    its parts removed: the Copilot extension and GitHub's `@vscode/copilot-api`
    (GitHub's own terms) and `terminal-suggest` (fish's completions, GPL-2). Git and
    the SSH client, GitHub's CLI, Docker's CLI with compose and buildx, and nothing
    more: an interpreter, a compiler or a database client comes in a container,
    which the Docker choice above allows, and keeps the GPL exception to git and the
    base system. PONISTRA's theme in both schemes, derived from `theme.css`; the
    scheme is the one chosen in PONISTRA's account menu, read from the same origin
    and followed live, else the system's. Telemetry, update checks and VS Code's own AI are off.
  - *Data.* `volumes/workspace` is the owner's home: the projects, VS Code's settings
    and extensions, the agent's sign-in and memory. The backup takes it with the rest.
  - *Git.* Repositories live in the workspace; a remote (GitHub, GitLab, a firm's
    own) is the owner's choice. Gitea was weighed and left out: for one person git
    and the backup already keep the history, the agents' cloud features work with
    GitHub alone, and its issues and wiki would double PONISTRA's tasks and
    documents. A mode in which nothing leaves the house fell with it: the agent
    sends the code it reads to its maker anyway, and a workspace cut off from the
    internet installs no package.
  - *Ivo's own*, the first elsewhere. Ivo's workspace on LXC 210 is the same image
    run from a directory of its own (`/mnt/docker/workspace`, with the host shell's
    tools layered on), as `bacinac` over `/home/bacinac` and `/mnt/docker` with the
    host's Docker: the dev PONISTRA it edits cannot be its door, and his production
    on mlaka will open it as its workspace elsewhere. It publishes no port; only the
    tunnel on LXC 210 reaches it, under the owner's code workspace name, which Cloudflare Access
    closes to Ivo's e-mail.
  - *Licences*, checked over code-server 4.144.0's 264 packages: 0BSD (tslib, which
    PONISTRA's charts already carried), BlueOak-1.0.0 (tar, minipass, lru-cache,
    chownr, yallist), Python-2.0 (argparse), the Unlicense (tweetnacl) and CC-BY
    (codicons, Git's logo) joined the rule, and git with the base system as its
    one GPL exception; jschardet is LGPL-2.1+, used unmodified.
- **D35: translating what arrives in another language — approved 2026-11-03** (Ivo: "a
  što misliš da dodamo auto translate dokumenata i mailova", then "slažem se sa svim"). A
  document is translated once and on purpose (D14's Translate into a new tab), so nothing
  translates documents by itself. What reaches a user in a language they do not read is
  mail and the files that come with it.
  - *The language.* Code knows a message's language on the server, from its text, through
    lingua (Apache-2.0, its high-accuracy models, about 80 MB): nothing leaves the
    installation for it. Croatian, Bosnian, Serbian and Montenegrin count as one, as no
    detector tells them apart in a short text and their reader reads them all. A text too
    short to tell has no language, and nothing is offered for it.
  - *What the user reads.* Settings → Translation holds the languages the user reads, by
    default the interface's alone, never English assumed; mail and files alike are offered
    translation only from another language, and always into the interface's. A message in
    another language shows Translate above it.
  - *Automatically.* A standing consent in Settings → Consents, off by default: with it, such a
    message opens translated, its original one click away. Without it, Translate asks as an
    action does, this once or always. With the installation's AI off, nothing is offered.
  - *When.* On opening, never on arrival: newsletters and junk the user never opens go
    nowhere.
  - *What goes.* The message as PONISTRA shows it (`safe.cleaned`), cut by code into its
    blocks, each block's links and formatting tagged in place as Translate into a new tab
    tags them, and the subject. Sonnet writes each block in the target language and code
    puts them back, so the layout, images and links stay. The translation is kept in
    Postgres beside the message, once for each language, and search finds the message by
    it too.
  - *A reply in the thread's language* (D35-2). The user writes in their own language;
    Translate reply, offered on a reply to a message in a language they do not read, shows
    the translation beside what they wrote, to correct before anything goes. Sonnet reads the
    message answered for its terms and how it addresses people; the subject, the blocks and
    the lines saying what the reply answers go through the same tags as reading. The message
    goes in the thread's language, and what the user wrote is kept as its translation into
    theirs, with the quoted message as they read it translated: their Sent folder shows and
    finds it in their words with no second call. The standing consent covers replies too.
  - *A PDF* (D35-3). Code tells the language of the file's text, its scanned pages read
    through OCR (D6), once the reading is over; a file in a language the user does not read has
    Translate into Croatian (the interface's language) in the PDF viewer's menu, into a new
    document beside the file, the document's own language set to it. Each page with text is an item of
    the queue that extracts data into a table (A5), so a long file goes on in the background,
    through a restart, under the same bar to stop, take back or open it. Sonnet gives a page's
    blocks (headings, paragraphs, list items, tables) through one tool, reading how the page
    before ended; a paragraph a page break cut in two is joined again, and the running header,
    footer and page number are left out. This covers the files that come by mail.
- **D36: boards — approved and built 2026-11-04** (Ivo: "a jel bi mogli dodati u ponistra,
  kao dokumente - artefacts koji bi claude generirao i da se spreme u ponistra", the name
  Ploča / Board agreed the same day). A board is a page of HTML an agent writes, or a user
  brings, shown as it is: a chart, a calculator, a dashboard, an explainer.
  - *What it is.* A file whose bytes are a page of HTML (`<!doctype html>` or `<html>`
    first, comments allowed) and whose name says `.html`, `.htm` or nothing: there is no
    kind of its own. An error page saved as `.json` stays text. The list calls it Ploča; the
    file page shows it, and its source on asking (Izvorni kod in the title's menu).
  - *Kept from PONISTRA.* PONISTRA shows a board in a page of its own (`/board`), whose
    policy allows one script, the bridge below, by its hash, and frames nothing but the board's
    page (`/board/page`, its exact address). That page is served sandboxed (`allow-scripts` alone) by its own headers
    too, so it runs in an origin of its own whoever opens it: no cookies, no storage,
    nothing of PONISTRA or the parent, no forms that send, no windows, and a link or a script
    that takes it elsewhere is refused before any request leaves. Scripts, styles and fonts
    load only from cdnjs, jsDelivr, unpkg, Tailwind's and jQuery's CDNs and Google Fonts, and
    a library fetches only from those: what the board shows belongs in the page itself, or in
    what it keeps. What browsers leave to no policy, WebRTC, stays open.
  - *Written by an agent* (D18). `write_board` makes a new board in a group, or replaces a
    board's page and keeps the one before; `read_document` gives the page back. A page is
    whole or refused, at most 1 MB.
  - *Versions.* A file's versions (`FileVersion`) keep each page with who wrote it and
    through which agent, the first as the file was made; Verzije on the file page lists them,
    shows one, and takes one back as a new version. Only boards are written over.
  - *Searched* by the text the page shows, not its source; what its script writes is not
    read.
  - *What a board keeps* (D36-2, built 2026-11-06, Ivo: "a sve odradi odavde"). A board keeps
    documents of JSON of its own by collection and key, each with a version (`BoardEntry`), so
    a page written once holds a plan that moves. A page reaches them through
    `window.ponistra.db` (`/api/boards/runtime.js`, the shape of an artifact's database), by
    messages to the bridge in the page around it, which alone has the session and calls only
    this board's data; an agent through `read_board_data` and `write_board_data`. Who reads the
    board reads them, who edits it writes them (`db.canWrite()` tells the page, so that it can
    disable what would be refused), and an old version only reads. A change reaches
    open pages through `/api/live`. A document is at most 256 KB, a collection at most
    10,000 of them, a call at most 500 writes, all or none.
  - *Later* (not approved): a board that reads PONISTRA's own tables, through a bridge the user
    allows table by table.
- **D37: a company's existing folders — approved 2026-11-05** (Ivo: "mislim da bi trebali
  imati opciju spajanja na postojeći workspace… te dokumente usisavamo u postgress i
  nastavljamo rad na njima"; the smaller scope and the copy agreed the same day). An
  organisation that installs PONISTRA keeps its documents on a file server or a NAS; they come
  in folder by folder, and once a folder is moved PONISTRA is its one source.
  - *One connector: SMB*, which every Windows file server, DFS share and NAS speaks
    (`smbprotocol` and `pyspnego`, MIT; NTLM, as Kerberos libraries come without wheels for
    Linux and every server takes NTLMv2). PONISTRA runs inside the organisation's network, so
    it reaches the server without anything opened or installed there. Clouds are left, not
    connected: a company leaving Microsoft 365 or Google brings its files through their own
    sync client and the folder upload, and S5 imports OneDrive through Graph as planned.
  - *Where.* A company folder (D20) is connected to a folder on a server: its address
    (`\\server\share\folder`), an account that may read it, its password sealed. The
    administrator alone connects, refreshes, moves and disconnects, from the folder's row.
  - *A copy until it is moved.* Connected, the company folder holds a copy of the server's
    folder: documents imported as an upload imports them, every other file kept as the file it
    is, read again when its size or time changes and taken away when it is gone. Nothing in
    it can be changed (every role in it reads), so the server stays the one source. Before the
    first copy the server's folder is read whole: files, folders and bytes, what stays out
    and why, and whether the disk holds it; copying waits for the administrator. *Move into
    PONISTRA* copies what changed last and ends the connection, and the folder is PONISTRA's.
    *Disconnect* takes the copy away.
  - *What stays out*, listed: a file or folder whose rights on the server are narrower than
    the folder above (its inheritance broken, or a right denied), which the administrator
    connects on its own to give it its own audience; one the account may not read; a path
    longer than PONISTRA keeps. Hidden and system files, names starting with a dot and
    Office's `~$` owner files stay out unlisted, as an upload leaves out a dot.
  - *Rights* are the company folder's, given to groups as for any company folder; nobody's
    are read from the server, so there is no directory to keep.
  - *An inbox.* A folder connected as an inbox moves each file that arrives in it into the
    company folder, as PONISTRA's, and deletes it on the server: what a scanner scans to a
    folder or an ERP exports. The account must be allowed to delete there; one that may not
    stops the inbox before anything is taken.
- **D38: PONISTRA signs users in to other applications — approved 2026-11-05** (Ivo: "a
  živcira me oval login na cloudflare kad želim do code… zašto ne dodamo lozinku na vscodeu
  koja bi se automatski učitala iz ponistra", the plan agreed the same day). An installation
  is an OpenID Connect provider, so an application of the organisation signs its users in
  with their PONISTRA account instead of a login of its own.
  - *Registered, not self-registered.* The administrator adds an application under *Prijava
    u aplikacije*: its name, the addresses it may be sent back to, and who may sign in to it
    (administrators by default, or all users). Its client id and secret are shown once; a new
    secret replaces the old one.
  - *The protocol* is the authorization code flow with PKCE (S256) where the application
    sends it, client secret by HTTP Basic or the form, ID tokens and access tokens signed
    RS256 with a key the installation makes and keeps sealed in its database. The issuer is
    `<PUBLIC_URL>/api/identity`, so its discovery, keys, token and userinfo stay under `/api`;
    only the sign-in is a page of the app (`/authorize`), which signs a user in first where
    needed, asks the D33 confirmation as opening the code workspace does, and sends the user
    straight back, with no consent screen, as the administrator registered the application.
    Refresh tokens are left out: an application keeps its own session and signs in again.
  - *First use:* the owner's code workspace (D34) on a host of its own sits behind
    oauth2-proxy (MIT) signing in here, which replaces Cloudflare Access in front of it, and
    is reached on the LAN directly.
- **D39: sharing outside the installation — approved 2026-11-05** (Ivo: "1 i 2 su mi
  interesantni", then "ove ideje možeš dodati u plan"). A document leaves the firm today only
  as a mail's attachment, a copy that drifts from its original; a link keeps the one original.
  - *A link is a grant.* An outside link is one more grant on a node (D11), with its roles. An
    open link, which anyone holding it may use, reads only, so a link that leaks changes
    nothing. A person named by their address gets a link of their own by mail, as a meeting's
    guest does (S2-2), may read or edit, and stands under their name in presence and versions.
  - *Limits.* A link may carry an end date, a password and *no download* (D20). Each opening,
    download and upload goes to the access log (D20), and its owner ends a link at once.
  - *Asking for files.* A folder's link may ask for files instead: whoever holds it uploads
    into that folder without an account, and the folder's owner is told. No virus scanner
    reads what comes in (ClamAV is GPL); it is read as a mail's attachments are, by the same
    readers in their own containers.
  - *Who shares outward* is the installation's policy, as D33's is: everyone (the default),
    administrators, or nobody.
  - *Attachments as links* (Ivo: "pa svi mi prijedlozi zvuče zanimljivo"). A file from the tree,
    or one too large to attach, goes in a mail as a link of each recipient's own, reading only
    unless the sender chooses otherwise: the recipient sees the file as it is now, and the
    sender sees who opened it.
  - *Built 2026-11-06:* the open link of a board (`OutsideLink`, `/o/<token>`), reading only,
    with an end date and a password, its openings in the access log, and the installation's
    policy. A password says nothing of the board before it is given. A folder that keeps things
    in the browser (D20) lets no link out. The token stands in plain text, in the database that
    holds the board anyway, so its owner can copy it again.
  - *Built 2026-11-10:* the rest. Whoever comes in from outside is a *visitor*, a `User` with
    `visitor` set and no password, whom `User.objects`, grants to everyone or a group, people
    lists and the sign-in page never reach; `api()` refuses a visitor every view that does not
    open itself with `visitors=True` (documents, files, versions, comments, help, exports where
    downloading is allowed). An open link (any node) signs the browser in as its own visitor,
    who goes with the link. A person shared with by address gets a grant with a key, mailed from
    the sharer's SMTP account as `/v/<key>`, and reads or edits under their name; a grant
    carries `download`. A mail carries nodes as links (`shared`): colleagues among its
    recipients get a grant, the rest one link of kind *people* per node that lets in only their
    addresses, each by a 6-digit code mailed from the sender's account (15 minutes, 5 tries, one
    a minute); the links are made only when the mail leaves and withdrawn when it does not, and
    a mail too large offers to send its files as links. A folder's *upload* link takes files
    into it without an account, in its creator's name, the sender's name in the access log, and
    its creator gets a push notice (`uploaded`) that opens the file.
- **D40: mail later and mail away — approved 2026-11-05, built 2026-11-08** (with D39). Each follows *the mail
  is ours* (D15, S3): the state lives in Postgres, and the provider is written to only by
  sending.
  - *Send later.* A message waits in PONISTRA and leaves from the user's account at the time
    chosen. One that fails stays among those waiting to be sent, with its reason, and the
    user is told.
  - *Snooze.* A message leaves the inbox and comes back to its top at the time chosen, with a
    notification; the provider's copy is not touched.
  - *Away.* PONISTRA itself answers from the user's account between two dates, as its sync
    runs on the server whatever the user's devices do: once per sender in the period, never
    to a list, bulk, `noreply` or automatic mail (RFC 3834; its own answer carries
    `Auto-Submitted: auto-replied`), with a text in Croatian and English. The provider's own
    vacation setting is not touched. Colleagues see the user away until that date in
    free/busy and in chat.
  - *Waiting for an answer.* A message sent may carry a date: if no one it went to has answered
    in its thread by then, it comes back to the top of the inbox, as a snoozed one does.
  - *As built.* One loop on the server does all four (`apps/mail/later.py`, listening and
    sweeping every 15 s). A message leaves at most once: a restart while it left puts it before
    the user, and nothing is retried by itself. A snooze is a folder of its own and `placed`
    sorts what came back to the top. An answer is a message in the thread from someone else, or,
    where a server writes Message-IDs anew (Traveler), one under its subject from someone it went
    to; what a program wrote and an emoji reaction are none. A message that comes back unanswered
    leaves Sent, as a message is in one folder. An away answer goes to the return path, or the
    sender where the server hands none over (ActiveSync), and holds both languages when both are
    written; it is judged as the message is taken and leaves from the loop, so no sync waits on a
    mail server. Colleagues see only the day it ends: `away` in `/api/calendar/free`, and in direct
    and group conversations, not channels.
- **D41: comparing with a file that comes back — approved 2026-11-05** (Ivo: "pa svi mi
  prijedlozi zvuče zanimljivo. uključi ih u plan"). A partner returns a contract as a Word file
  without tracked changes. *Compare with file* (action `file.compare`, `apps/versions/compared.py`)
  reads it as the import does, without making a document of it, and code finds where it differs
  from the tab: the texts of paragraphs, headings and tables aligned in order, a changed stretch
  paired block to block by likeness. Each difference comes as a proposal (D14) under the file's
  name, accepted or rejected one by one: a block with other words rewritten word by word, one the
  file lacks deleted, a run of the file's own inserted where it stands there, a changed table
  deleted and the file's put after it. No model takes part, as a rule finds every difference.
  Any text the import reads can be compared (docx, odt, doc, rtf, another PONISTRA document, its
  tab of the same name or its first), and a file from the computer is kept as it came in the
  document's folder, so the action always names a node the user reads.
- **D42: finding a time — approved 2026-11-05** (with D41). The event's form now only says who
  is busy at the time chosen; it offers instead the first times at which everyone invited from
  the installation and every room chosen are free for the event's length, from the free/busy
  it already knows (S4), on its working days (S4) and within its working hours, a setting kept
  beside its days off. People from outside are shown as unknown, never guessed; choosing an
  offer sets the time. The offers appear only when the time chosen clashes (someone invited busy
  or away, a room ticked taken), for the user, everyone invited from the installation and the
  rooms ticked: the first six that do not overlap, on the half hours from the opening, from the
  day chosen (from now once it has begun) up to two months ahead, time away (D40) counting as
  busy. The working hours (default 08:00–16:00, on the installation's clock) sit in `Workdays`
  and move no series; `/api/calendar/free` answers the offers when asked for them.
- **D43: scanning with the phone — approved 2026-11-05** (with D41). *Scan* in the app on a
  phone (D26, and the web app in any phone's browser) takes pages with the camera. The reader
  (D51) finds each page's corners (numpy and Pillow), the user may move them, and the page is
  straightened and its paper evened out to white (Pillow); the pages become one PDF whose text
  the OCR reads (D6) before it lands, into the folder chosen or as a mail's attachment. OpenCV
  stays out: its Python wheels ship FFmpeg under the LGPL; so does scikit-image, as it needs
  scipy, whose wheels bring OpenBLAS with libgfortran (GPL), the reason numpy is built without
  BLAS.
- **D44: leaving Google Workspace — approved 2026-11-05** (with D41), as part of S5, which does
  the same for Microsoft 365. Each user takes their Drive and the shared drives they see through
  the Drive API: Google Docs, Sheets and Slides exported as docx, xlsx and pptx and imported,
  every other file as itself, the folders as they were, and who may open what as grants where
  that person is a user of the installation. Each pass takes only what changed, so both run side
  by side until the subscription ends. Mail, calendar and contacts already come through the
  accounts (S3, S4). It goes through the installation's own Google client (S3-4), whose consent
  screen is Internal in the organisation's Workspace, so Drive's restricted scope asks for no
  verification.
  - *Built 2026-11-11* (`apps/drive`, *Postavke → Preseljenje → Google Drive*). The Google sign-in
    of a mail account asks for `drive.readonly` beside mail and contacts; an account connected
    before signs in again. The first pass lists the space whole after taking Google's start page
    token, each later one only `changes` since it, every `DRIVE_SWEEP` (5 min) and at once on
    request. A file whose checksum (or, for Google's own formats, time of change) is unchanged is
    only moved, renamed and granted, never downloaded again.
  - *Copied, read only.* Each space (the user's My Drive, a shared drive) is a folder at the top of
    its taker's documents, `copied` as D37's copy is, so every role in it reads while Google stays
    the original. *Finish* takes the last changes and leaves the folders the users'; *cancel*
    deletes what was taken, nothing changes at Google.
  - *A shared drive once.* It is copied by the first member whose pass reaches it and reached by the
    other members through grants; when its taker lets go or loses it, the next member's pass takes
    it over.
  - *Grants.* A permission of a user whose address is an installation user's (their own, or a Google
    account they connected) becomes a grant, owner and organiser `own`, file organiser and writer
    `edit`, commenter and reader `read`, on a node only where it reaches beyond what the folders
    above give. Groups, domains and links stay out, as do comments and Google's version history.
    In a shared drive, whose listing carries no permissions, an item's are asked for only where its
    permission ids are not all its folder's.
  - *Left out, with why:* shortcuts, Google formats with no export (forms, sites, maps), files whose
    owner disabled downloads, files beyond the installation's size limit.
- **D45: working without the network — approved 2026-11-05** (with D41). A device the user marks
  for it keeps documents and mail, so they are read and written without the network, and what
  changed joins the rest when it comes back.
  - *Documents.* Each tab's Yjs state is kept in the browser (y-indexeddb, MIT), and edits made
    offline merge as any co-editor's do (D2). Kept are the tree, the documents opened recently
    and those the user marks.
  - *Mail.* The recent mail with its attachments is read from the device; what is written waits
    and leaves when the network returns, through the queue D40 sends later by.
  - *Limits.* What needs the server (search, actions, AI, meetings) is disabled while offline,
    not refused after a try. A folder with *no download* (D20) is never kept; signing out empties
    the device, and ending it in the list of devices (D20) empties it at its next connection.
  - *Documents, built 2026-11-11.* The device is marked on itself, in Settings → devices
    (`Session.offline`, kept in the session's data; the list shows it to the user and the
    administrator). It keeps the server's answers the tree and a document read (`kept.ts`), each
    kept document's rooms in y-indexeddb, the documents marked in a folder's row menu (in the
    browser, per device) and the whole app: the build lists its files in `/assets.json`, the
    service worker serves them from its cache and the app's page when the server is not there.
    A pass runs on opening, on reconnecting and a minute after the tree changes; a failed one
    says why. *Reachable* is the `/api/live` socket being up, or refused (4403) because nobody is
    signed in on the tab, as a meeting's guest, a visitor or the sign-in page; search, the backend's actions, a new
    document or note and every change in a folder are disabled while it is down, as are a
    meeting's entry points (S2's chat). Any answer that nobody is signed in empties the device, so
    signing out, an ended device and a session run out are one rule. Sheets stay with the server
    (D22): offline, text and presentations are written, files and PDFs are not kept.
- **D46: the list of boards — approved and built 2026-11-05** (Ivo: "a što je s onim planom da
  imamo liste artefacta kao podgrupu u dokumentima … i moraju prikazivati html"). *Ploče* in the
  column of Dokumenti (`/boards`) lists every board the user can read, whichever folder keeps it,
  under the same rights and row actions as any list. It is a view: a board stays in its folder,
  with no copy and no folder of its own, unlike Poveznice (D31), whose page is their folder.
  D47 gave boards that place, so the list is no longer a view across folders.
  - *It shows them.* The list is there for what the boards show, so the preview panel opens
    on it wide (a width of its own, up to half the row), on the first board until one is chosen,
    and the list keeps only the name and the date, the panel saying the rest. On a phone a tap
    opens the board, as in any list.
  - *Kept in the browser.* As the list crosses folders, each board says whether a folder on its
    way keeps it there (D20), and its download and copies are disabled by that.
- **D47: boards in a place of their own, by project — approved and built 2026-11-06** (Ivo: "a
  zašto imamo boards i pod documents i samostalno. trebale bi biti samo pod baords i da budu
  grupirane po projektu koji ih je kreirao. također da se isto učitaju u postgress da znamo i po
  njima pretraživati"). The view of D46 and a folder named Ploče showed the same boards twice.
  - *Language and theme.* The account keeps them (`User.language`, `User.theme`, empty while not
    chosen), so every device shows the same and a change reaches the others live; the account wins
    over the browser, which holds both only for the sign-in page. An account that holds nothing takes
    what the browser already chose. The printer's page ignores them.
  - *The name of a place.* Bilješke, Poveznice and Ploče are named by the interface in its language,
    by the place's flag (`stepTitle`), wherever a way shows them; the title a place keeps is a neutral
    `Notes`, `Links`, `Boards` no one reads, and a search does not find a place by it. A group and
    a link keep the words the user gave them, as these are content.
  - *The place.* As Poveznice (D31): one top-level folder per user (`Node.boards`), never shown
    among the documents or offered by a dialog that picks a folder, whose folders are its groups.
    *Ploče* lists the boards in it under a heading per group, then what others share from theirs,
    which no longer also shows under Dijeljeno. It takes only boards. A page of HTML kept anywhere
    else is a file like any other, shown as a board when opened, and joins through *Grupa na
    Pločama…* in its row's menu.
  - *The group.* The server cannot tell which project an agent works in, so the agent names it:
    `write_board` refuses a new board without a group, and `move_board` moves one without passing
    its page again. A name is matched whatever its case and made if missing. A heading's long
    press renames or trashes the group, and a group left empty shows no heading.
  - *Found.* What a page shows has been in Postgres since D36 (`search_blobpage`); its bytes stay
    in the blob store, as every file's do, since a second copy would find nothing more. What a
    board keeps is found too, by the strings in its JSON (`board_text`, a generated and indexed
    `words` on `BoardEntry`), and such a hit says `source: data`.
  - *Links to artifacts* left the list: they stay in Poveznice, which keeps one item in one place.
  - *A page's charset.* A page is served with the charset its bytes are in, as one that names none
    would otherwise be read as Windows-1252.
- **D48: favourites — approved and built 2026-11-06** (Ivo: "a jel bi favorite oznaku mogli ubaciti
  i u dokumente, mailove, boardove - kroz cijelu aplikaciju"). A mark is worth what finding the marked
  gives, so each kind got both, in the place the user already looks for it. *Omiljeno* is the one
  name of the one star.
  - *Documents, files, folders, links and boards.* A row of its own per user and node
    (`Favourite`), not a field on the node, as a shared document is the same for all who hold it. The
    star stands in a row's menu and in the header of what is open. *Omiljeno* leads the side column
    (`/favourites`, under a heading per place) and shows on Today once it holds anything. What goes
    to the trash or is no longer shared leaves the list and returns with it.
  - *Notes.* Their pin was the same thing kept on the node, so it became the star, and a note marked
    comes first among the notes.
  - *Mail.* The flag it already had, which stays in Ponistra as every flag does, with the list it
    lacked: *Omiljeno* under the Inbox holds the flagged messages of every folder but Trash and Junk.
  - *Contacts* keep their star, which goes to the phone. *Calendar, tasks and chats* have none: they
    are found by date and person, and a star there would only add noise.
- **D49: built-in help — approved 2026-11-07** (Ivo: "pokriti detaljno sve funkcije i paziti da se
  ažurira kako se mijenja kod"). A help that is written apart from the code goes stale unnoticed, so
  it lives in the repo, ships with each release and stops a push when it no longer tells the truth.
  - *Articles.* `help/<section>/<slug>` holds a record (`.json`) and a text per language (`.hr.md`,
    `.en.md`) under four fixed headings: how to use it, how it works, limits, related. Interface names
    are not typed but named by their i18n key (`{t:mail.send}`), so an article cannot call a button
    what it no longer is. `help/README.md` is the writers' rule book.
  - *Where it opens.* Only on request (`/help`, the account menu, F1 for the page in use, the search
    box and its results, MCP `search_help` and `read_help`), never as hints in the interface.
  - *The gate* (`scripts/help.py`, in each push and each night). The inventory comes from the code:
    routes, settings, actions, MCP tools and every interface string. Each must be in an article or
    deliberately left out, which also keeps the depth equal whoever writes. Each article notes a
    fingerprint of the code it describes (`describes`); when that code changes the push stops until
    the article is read again and sealed (`help.sh seen`). The two languages must name the same
    labels, shortcuts, links and pictures, with as many steps. `help/uncovered.txt` holds what is not
    yet written, may only shrink and goes when empty.
  - *Pictures* are never drawn by hand. `manage.py help_seed` fills one account per language with
    invented data, `e2e/shots/` takes each picture in both languages and schemes (`check.sh --shots`,
    each night), `help-shots/` is not committed and a release carries the latest. A picture that is
    missing shows its description.
- **D50: a person's data, exported and erased — built 2026-11-10** (analysis findings U2, U3, N8).
  The organisation that installs Ponistra is the controller and answers a person's requests under
  GDPR through its administrator, so both live on the page of users, behind a recent confirmation
  (D33).
  - *Export (art. 15 and 20).* A job (`personal`, `apps/users/personal.py`) makes one zip: the
    account, every row of every model that names the person as JSON by model and field, each
    message of their mail as it came (`.eml`), their contacts' photos, and their own documents as
    Ponistra files and their own files as they are, by folder. Every relation to a user is either
    exported or left out with its reason (`PARTS`, `LEFT`), and a test fails when a new one is
    neither; secrets that sign in or open something (digests, session keys, tokens, binary keys) are
    never written. The vault is sealed in the browser and exports itself.
  - *Erasure (art. 17)* is deletion, not anonymisation: the database's own cascade removes what is
    theirs alone and empties their name from what they wrote for others (chat, comments, logs).
    What nobody else owns is not lost: the administrator names an heir, the person's own top-level
    documents and folders move into one folder named after them at the top of the heir's documents
    (their notes, links and boards becoming plain folders), and a company folder they alone owned
    gets the heir as owner where it stands. A shared vault collection they alone own stops the
    erasure, as its key is sealed to its members. Names inside a document's content (proposed
    changes) are the document's and stay.
  - *Sessions* last at most 30 days from sign-in however busy (`sessions.LASTS`), beside Django's 14
    days without use, so a session someone took does not live on by being used. *A meeting's door*
    holds at most 20 guests come by its link in the last 10 minutes; those asked by mail are not
    counted.
  - *Files after erasure.* A file of the person's that nothing names any more waits 7 more days in
    the store's `dead/`, as long as a restore to a moment reaches back (S8), the same as in the
    snapshots, and is then deleted.
- **D51: files someone else made are read in a reader of their own — built 2026-11-10** (analysis
  finding S4, Ivo: the whole proposal accepted). PDFium, Pillow, pikepdf and lxml over a user's
  Office file ran inside the backend, which holds `SECRET_KEY`, the mail accounts' keys and the
  database: one fault in one of them, over a file anyone can upload or mail in, reached all of it.
  - *The service* `reader` (`apps/reader/`) runs the backend's own image with `PONISTRA_ROLE=reader`:
    no secret in its environment, no database, no blobs, a read-only root, every capability dropped,
    a network (`read`) that reaches only the backend. Each request gets a process forked from the
    server and each reading a process forked from that, under 3 GiB of address space, a processor
    time of its kind and no core file; a reading the kernel ends is answered as too large (memory,
    time) or unreadable (any other signal), and only that process ends. At most three read at once.
  - *What passes* is a head of JSON and the files, and back lines of JSON, each value of a closed
    set of types (`wire.py`: the import's dataclasses, tuples, sets, bytes, dates), a file as its
    length and its bytes; never pickle, so a reader a file took over cannot run code in the
    backend. A failure comes back by name and is raised as the exception the backend already knows
    (`reads.FAILURES`); a name the backend does not know is a fault, never a silent default.
  - *What reads there:* every import (Word, Excel, PowerPoint, CSV, the converter's output), the
    text of a PDF and its search, previews, a contact's photo, a link's icon, an image edited, a
    PDF's sizes and pages for exports, annotations and embedded files written into a PDF, pages
    composed and blacked out, an original's macros carried into an export, and the content type an
    Office file names for its main part. `@alone` went with it: each reading is a process of one
    thread.
  - *A workbook streams through it.* The reader parses and types the rows and encodes them as
    Postgres keeps them (`laying.Laying`); the backend only writes them (`laying.written`).
    Measured on 100,000 rows × 10 columns of CSV: the reader 32 s (parsing and typing 28 s,
    encoding 0.5 s, JSON 3.5 s), the backend's writing 13.6 s, 49 s in all; reading ahead in a
    thread of the backend gained nothing and is not kept. Sending recorded operations instead of
    rows would move the encoding into the backend and gain nothing either.
  - *Boundaries, read in the backend on purpose:* the PDF our own printer made
    (`documents/printing.py`, `exports/embedded._wanted`), migration 0025 (already run on every
    installation), the protocols' XML: CalDAV and CardDAV through Python's expat, which limits
    entity expansion itself, and a mail server's autodiscover (`mail/servers.py`) through lxml
    without entities or network, each from a server the user configured or a client signed in;
    the format `.ponx` (Python's own json and zipfile over our own format) and the zip and OLE
    listing that tells a file's kind (pure Python). The browser's tests note what they ran in the backend's
    process, not in the reader's.
- **Retention rules and legal holds — built 2026-11-10** (analysis finding U4). Each installation
  decides how long its content stays, and a dispute stops deletion until it is settled.
  - *A rule* (`apps/retention`, the administrator's page `/retention`) covers documents, files,
    mail or chat, and documents and files may also be covered per folder. It names how long the
    content is kept at least and when it is removed. Of the keeping periods that apply, the
    longest wins. The removal period is taken from the rule nearest the content and is never
    shorter than the keeping period.
  - *A legal hold* covers one person or one folder. It keeps whatever that person wrote, owns or
    took part in, or whatever lies in that folder, until the administrator releases the hold.
  - *Every place that deletes for good* asks `retention/kept.py` first and is refused with 409
    `held` or `retained`. That covers emptying the trash, deleting mail, deleting or taking back a
    chat message and removing a conversation, erasing a person (D50), disconnecting a copy of a
    file server's folder and deleting a company folder. A copy keeps what is kept even after it
    disappears from the server. A held folder or person is named by a foreign key without a
    cascade, so a deletion that skipped the check fails loudly instead of losing the content. An
    edit of a chat message is refused only under a hold.
  - *Removal* runs as a loop every hour (`sweep.py`). It deletes what a rule's removal period has
    reached and records how much it removed of each kind. Mail is forgotten as a delete in the
    mail client would forget it.
- **D52: the Kod page is the owner's desk over the workspace's chats — built 2026-11-11** (round
  ponistra-20261111-1826, steps KR7–KR12). Ivo runs five or six projects in parallel from a phone;
  the page grows from a list of chats into the place he talks to them, answers them and lets a
  round finish without him.
  - *Every action is a command* (`apps/workspace` model `Command`): starting, consolidating or
    pushing a round, its switch to consolidate by itself, a message or a Yes/No to a chat,
    archiving a chat and the workspace's restart. A command is a row in Postgres with its outcome
    (sent, taken, done, failed with a code) and its time, shown in the page's activity live through
    `/api/live`; the backend hands it to the workspace (`POST /ponistra/commands`), whose service
    keeps it as a file under `~/.claude/ponistra-commands/` and reports each move back in its
    `changed` call. A state only moves forward. Push and restart ask for a fresh confirmation (D33).
  - *A chat is talked to without any API.* The page reads a chat's transcript from the workspace
    (`GET /ponistra/chats/<id>`, the latest 100 messages, tool calls folded). No Anthropic API,
    Agent SDK (its licence is not permissive) or Remote Control: the work stays in the owner's
    subscription and in the transcript he would see anyway.
  - *The workspace runs the chats, not the editor* (KR19, 2026-11-12). The service
    (`workspace/chats.mjs`) holds one Claude Code process per chat, the extension's own binary
    started as its panel starts it (stream-json in and out, permissions over stdio, `auto` mode,
    `CLAUDE_CODE_ENTRYPOINT=claude-vscode` so it registers in `~/.claude/sessions`). A new chat or
    round, a message with up to four images (PNG, JPEG, GIF, WebP, each ≤ 3.75 MB, uploaded by the
    owner and sent base64 as `image` blocks), Yes/No, a name, closing and archiving go straight to
    that process; none opens the editor. The chats it runs are kept in `~/.claude/ponistra-hosted.json`
    and resumed when the service starts. "Otvori chat" (`open`) lets the process go first and is
    refused (`chat_working`) while the chat works or waits, so one session never runs in two
    processes; should it all the same (an editor window kept alive by the 3-day reconnection
    grace), the service ends the older idle process. A message to a chat working in the editor
    waits until it is idle, then takes it over (`chat_busy` after an hour).
  - *Yes / No* answer the process's permission request or question (`control_response`); a
    question with offered answers can be answered in words through a message. A chat waiting on
    its owner stands under "Čeka vas" with what it asks.
  - *Archive* ends the chat's process wherever it runs; an editor window that brings back an
    archived chat's tab when it loads closes it, and the chat drops among the closed ones.
  - *Hearing the coordinator:* Claude Code's `Stop` and `Notification` hooks, configured in the
    workspace image's managed settings, write `~/.claude/ponistra-heard/<session>.json`; a change
    for a round's coordinator becomes a push to the owner (what it said, or that it waits) from
    `apps/workspace/notices.py`. The push of a chat or coordinator that waits carries Yes and No
    (KR13): the service worker answers as the page's Yes/No would, `POST /api/workspace/commands`
    with the session the notice names, and opens the Code page only when the answer fails.
  - *A round* is the file `~/.claude/ponistra-rounds/<round>.json` the `nastavi` skill writes. The
    service names its coordinator once (`named`), starts its chats once it is `started`, each with a
    session id it assigns, and ends them once it is `closed` (`ended`); each panel only draws the
    round as a group in its list of sessions. No window owns a round (KR14's `claim` is gone).
  - *Consolidate by itself* is on for each round unless switched off. When every chat of a round
    is done and its coordinator idle, the backend sends the coordinator "objedini sam od sebe"
    once; the `objedini` skill then runs without asking, and any question, error or chat still at
    work stops it with a notice, the round waiting for its owner. A push never goes by itself.
  - *The agent's memory* (MEM1–MEM5, 2026-11-12). The memory files stay the source; Postgres
    (`apps/memory`) keeps only proposals, their history and what was last analysed. The workspace
    (`workspace/memory.mjs`, routes `/ponistra/memory`, `memory/file`, `memory/write`) reads every
    store under `~/.claude/projects/` (alias symlinks skipped): files, the lines and tokens
    `MEMORY.md` adds to each session, mechanical findings and mechanical proposals (git state, a
    stale path, UTC to CET/CEST, links, index lines, frontmatter), with no model. It watches the
    stores and calls `/api/memory/changed` with its token. A proposal holds the hash of the text it
    was made from; the workspace writes it (tmp + rename) only while the file still has that hash,
    else, when the change since touched other lines (another proposal for the file accepted), it
    is laid over that change line by line, and only a change on the same line makes it stale and
    a mechanical one is made again. Reverting goes the same way. A UTC time is converted only on a
    line that names its day; one without a day recurs and stays in UTC. The open proposals are
    reviewed (MEM6, 2026-11-13) by a chat the same way: it reads them as excerpts through the MCP
    tool `memory_proposals` and sends groups, each with a title, a reason and an advice (accept,
    reject, look at each), through `advise_memory`, replacing the groups before; the owner
    accepts or rejects a group at once, its proposals written in the order they were made.
    The semantic analysis (duplicates, contradictions with `CLAUDE.md`, rules in three or more
    stores for the global `CLAUDE.md`, long index lines) is a chat the Pult starts in the workspace
    on the subscription, over the files whose hash changed since the last analysis; it proposes only
    through the MCP tool `propose_memory`, which takes the workspace owner alone. New proposals
    reach the owner as a push with Yes and No; a nightly pass at 04:00 runs only when switched on.
    The owner's workspace door must let the three memory routes through to the token.
  - *A terminal* per project (KR25, 2026-11-12): xterm.js in the page, a WebSocket to the backend
    (`/api/workspace/terminal`, only under a fresh D33 confirmation, which a POST to the same path
    asks for first), relayed with the token to the workspace's `/ponistra/terminal`
    (`workspace/terminal.mjs`), where a login shell runs in a pseudo-terminal in the project's
    folder for as long as the socket lives. node-pty and ws come from code-server itself, so the
    image needs no build tools. Binary frames carry what is typed and shown, a text frame
    `{cols, rows}` resizes; the socket closes with 4000 once the shell exits.
