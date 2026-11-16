"""The code workspace the demo's Projects page shows: Sarah's, with three of the studio's software
projects and the general one, chats running in them, a round under way, one done and waiting to be
closed and one waiting for the weekly limit to begin anew, a chat waiting for each morning, the
agent's memory, a project's plan, and the time worked and the tokens taken since late summer with
the plan's limits as they were measured.

The workspace's files are written only where the installation names the account as its owner
and its workspace holds nothing yet (scripts/demo.sh); `e2e/demo/workspace.mjs` then makes each
project a git repository with its uncommitted changes, runs a process for each running chat in
Claude Code's register and stands in for the agent's report of the plan's limits, all from
`MANIFEST`."""

import json
import os
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.ai.model import CACHE_WRITE, PRICES
from apps.documents import boards, boards_place
from apps.documents.models import Node
from apps.documents.views import created
from apps.workspace import worked
from apps.workspace.models import Command, Limits

from .company import Seeded

HOME = "/home/sarah"
MANIFEST = ".demo-workspace.json"
IDS = uuid.UUID("5a2b6f1e-2d7c-4f0e-9a51-3c8e0d4b7a10")
OPUS, SONNET = "claude-opus-5-5", "claude-sonnet-5-5"

# The plan's limits as the agent reports them: a window's use in percent and its end in minutes
# from when it is read.
USAGE = {
    "five_hour": {"utilization": 34, "resets_in": 128},
    "seven_day": {"utilization": 31, "resets_in": 3 * 24 * 60 + 410},
    "model_scoped": [{"display_name": "Opus", "utilization": 38, "resets_in": 3 * 24 * 60 + 410}],
}
MODELS = [
    {"value": "opus", "displayName": "Opus 5.5", "resolvedModel": OPUS},
    {"value": "sonnet", "displayName": "Sonnet 5.5", "resolvedModel": SONNET},
    {"value": "haiku", "displayName": "Haiku 5.5", "resolvedModel": "claude-haiku-5-5"},
]


@dataclass
class Turn:
    """The owner's words this many minutes ago, the tools the agent used and its answer, or none
    while it still works."""

    ago: int
    said: str
    tools: list[tuple[str, dict]] = field(default_factory=list)
    answer: str | None = None
    took: int = 6


@dataclass
class Chat:
    key: str
    project: str
    title: str
    turns: list[Turn]
    model: str = OPUS
    # Claude Code's register: busy, idle or waiting, or None for a chat no longer running.
    status: str | None = "idle"
    waiting_for: str | None = None
    name: str | None = None
    context: int = 60_000

    @property
    def id(self) -> str:
        return str(uuid.uuid5(IDS, self.key))

    @property
    def folder(self) -> str:
        return f"{HOME}/{self.project}" if self.project else HOME


def edit(project: str, path: str, description: str = "") -> tuple[str, dict]:
    return ("Edit", {"file_path": f"{HOME}/{project}/{path}", "description": description})


def run(command: str, description: str) -> tuple[str, dict]:
    return ("Bash", {"command": command, "description": description})


def read(project: str, path: str) -> tuple[str, dict]:
    return ("Read", {"file_path": f"{HOME}/{project}/{path}"})


ROUND_TASKS = (
    (
        "grid",
        "**Portfolio grid with filters.** On /work, the projects as a grid of cards filterable "
        "by room type and year, the filter kept in the address. Area: `src/components/`, "
        "`src/pages/work.astro`.",
    ),
    (
        "lovran",
        "**Case study: Villa Lovran.** A page of its own from the photos and notes in "
        "`content/lovran/`, the before and after slider included. Area: `src/pages/work/`.",
    ),
    (
        "spam",
        "**Contact form without spam.** A honeypot field and a time check before the form "
        "sends, no third-party captcha. Area: `src/pages/contact.astro`, `functions/`.",
    ),
)

PLANNER_TASKS = (
    (
        "cache",
        "**Plans kept offline.** The plans a client opened stay readable without a network, "
        "from the browser's own store. Area: `src/store/`.",
    ),
    (
        "sync",
        "**Edits made offline.** What was drawn without a network is sent once it is back, a "
        "wall moved by someone else meanwhile kept as theirs. Area: `src/sync/`.",
    ),
)

QUOTE_TASKS = (
    "**VAT by the client's country.** Quotes for clients in the EU outside Croatia apply the "
    "reverse charge and say so on the quote. Area: `quotes/tax.py`.",
    "**Price list import.** The suppliers' price lists (CSV and Excel) read into materials, "
    "with the date each price was valid. Area: `quotes/materials/`.",
    "**Quote PDF on the studio's letterhead.** Logo, address and bank details, items grouped "
    "by room. Area: `quotes/pdf/`.",
)

CHATS = [
    Chat(
        "website-coordinator",
        "website",
        "Spring portfolio",
        [
            Turn(
                175,
                "Plan the spring portfolio update for the website: the grid, the Lovran case "
                "study and the contact form. Split it into chats by area.",
                [read("website", "README.md"), run("git log --oneline -15", "Recent history")],
                "Three chats, one per area, none touching another's files: the grid "
                "(components and /work), the Villa Lovran case study (a page of its own) and "
                "the contact form (form and function). I'll consolidate when all three are done.",
            ),
            Turn(
                22,
                "How far are they?",
                [],
                "The contact form is done and checked. The grid is filtering by room type and "
                "now adds the year. The Lovran page is waiting for you to allow the build.",
                took=2,
            ),
        ],
        name="Spring portfolio",
        context=48_000,
    ),
    Chat(
        "website-grid",
        "website",
        "Portfolio grid with filters",
        [
            Turn(
                168,
                ROUND_TASKS[0][1],
                [
                    read("website", "src/pages/work.astro"),
                    edit("website", "src/components/ProjectGrid.astro", "Grid of project cards"),
                    edit("website", "src/data/projects.ts", "Room type and year per project"),
                    edit("website", "src/pages/work.astro", "Filters kept in the address"),
                    run("npm run check", "Type check"),
                ],
                "The grid is in, filterable by room type, with the filter in the address "
                "(`/work?room=kitchen`). Next: the year.",
                took=40,
            ),
            Turn(
                9,
                "Add the year as a second filter, newest first.",
                [edit("website", "src/components/ProjectGrid.astro", "Year filter")],
            ),
        ],
        status="busy",
        context=112_000,
    ),
    Chat(
        "website-lovran",
        "website",
        "Case study: Villa Lovran",
        [
            Turn(
                166,
                ROUND_TASKS[1][1],
                [
                    run("ls content/lovran", "Photos and notes of the project"),
                    edit("website", "src/pages/work/villa-lovran.astro", "Case study page"),
                    edit("website", "src/components/BeforeAfter.astro", "Before and after slider"),
                    run("npm run build", "Build the site"),
                ],
            ),
        ],
        status="waiting",
        waiting_for="Bash: npm run build",
        context=86_000,
    ),
    Chat(
        "website-spam",
        "website",
        "Contact form without spam",
        [
            Turn(
                164,
                ROUND_TASKS[2][1],
                [
                    edit("website", "src/pages/contact.astro", "Honeypot field"),
                    edit("website", "functions/contact.ts", "Refuse forms sent too fast"),
                    run("npm test -- contact", "Tests of the form"),
                ],
                "Done: a hidden field bots fill in and a form sent within three seconds of "
                "loading are both refused quietly; the tests cover both and a real sending.",
                took=25,
            ),
        ],
        status=None,
        model=SONNET,
        context=41_000,
    ),
    Chat(
        "planner-snap",
        "planner",
        "Snap furniture to walls",
        [
            Turn(
                95,
                "When a piece of furniture is dragged within 10 cm of a wall, snap it flush "
                "against it, rotated to the wall's angle.",
                [
                    read("planner", "src/plan/walls.ts"),
                    edit("planner", "src/plan/snap.ts", "Snap to the nearest wall"),
                    edit("planner", "src/plan/drag.ts", "Use the snap while dragging"),
                    run("npm test -- snap", "Snap tests"),
                ],
                "Furniture now snaps flush to a wall within 10 cm and takes its angle; holding "
                "Alt drags freely. Tests cover straight, slanted and corner walls.",
                took=35,
            ),
        ],
        context=73_000,
    ),
    Chat(
        "planner-pdf",
        "planner",
        "Export a plan as PDF",
        [
            Turn(
                31,
                "Export the current plan as a PDF at 1:50 on A3, with the room names, areas "
                "and a scale bar.",
                [
                    read("planner", "src/export/svg.ts"),
                    edit("planner", "src/export/pdf.ts", "Plan to PDF at a given scale"),
                ],
            ),
        ],
        status="busy",
        model=SONNET,
        context=58_000,
    ),
    Chat(
        "planner-coordinator",
        "planner",
        "Offline plans",
        [
            Turn(
                150,
                "Plan offline use for the planner: plans readable without a network and edits "
                "sent once it is back. Split it into chats by area.",
                [read("planner", "README.md"), run("git log --oneline -10", "Recent history")],
                "Two chats, one for the plans kept in the browser and one for sending the "
                "edits made offline. I'll consolidate when both are done.",
            ),
            Turn(
                14,
                "Consolidate them.",
                [
                    run("git merge --no-ff round/cache round/sync", "Merge both chats"),
                    run("npm test", "All tests"),
                ],
                "Both merged into main and all tests pass; the plan and the memory are written. "
                "Nothing is left in this round, so it can be closed.",
                took=8,
            ),
        ],
        name="Offline plans",
        context=54_000,
    ),
    Chat(
        "planner-cache",
        "planner",
        "Plans kept offline",
        [
            Turn(
                144,
                PLANNER_TASKS[0][1],
                [
                    edit("planner", "src/store/plans.ts", "Plans kept in IndexedDB"),
                    run("npm test -- store", "Store tests"),
                ],
                "A plan opened once stays readable offline, the newest twenty kept.",
                took=30,
            ),
        ],
        status=None,
        model=SONNET,
        context=39_000,
    ),
    Chat(
        "planner-sync",
        "planner",
        "Edits made offline",
        [
            Turn(
                143,
                PLANNER_TASKS[1][1],
                [
                    edit("planner", "src/sync/queue.ts", "Edits queued while offline"),
                    run("npm test -- sync", "Sync tests"),
                ],
                "Edits made offline are queued and sent in order once the network is back; a "
                "wall someone else moved meanwhile stays theirs and the edit is shown as declined.",
                took=45,
            ),
        ],
        status=None,
        context=67_000,
    ),
    Chat(
        "quotes-coordinator",
        "quotes",
        "Quotes for spring",
        [
            Turn(
                24,
                "Divide the next round for quotes: VAT by country, the suppliers' price lists "
                "and the PDF on our letterhead.",
                [read("quotes", "README.md")],
                "Three chats ready, one per area. They start when you press Start.",
                took=4,
            ),
        ],
        name="Quotes for spring",
        context=32_000,
    ),
    Chat(
        "general-hours",
        "",
        "Hours for Marta",
        [
            Turn(
                55,
                "Make the table of last month's hours by project for Marta.",
                [run("ls", "Projects in the workspace")],
                "Done: October by project, with the days each was worked on; it is in "
                "Finance as “Development hours, October”.",
                took=5,
            ),
        ],
        model=SONNET,
        context=22_000,
    ),
]

FILES = {
    "website": {
        "README.md": "# Lipa Studio website\n\nThe studio's Astro site, deployed on every push.\n",
        "package.json": '{\n  "name": "lipa-website",\n  "private": true,\n  "scripts": {\n'
        '    "dev": "astro dev",\n    "build": "astro build",\n    "check": "astro check",\n'
        '    "test": "vitest run"\n  }\n}\n',
        "src/pages/work.astro": "---\nimport Layout from '../layouts/Layout.astro';\n---\n"
        '<Layout title="Work">\n  <h1>Work</h1>\n</Layout>\n',
        "src/data/projects.ts": "export const projects = [\n"
        "  { slug: 'villa-lovran', title: 'Villa Lovran' },\n"
        "  { slug: 'hotel-obala', title: 'Hotel Obala, lobby' },\n];\n",
        "src/pages/contact.astro": "---\nimport Layout from '../layouts/Layout.astro';\n---\n"
        '<Layout title="Contact">\n  <form method="post" action="/contact"></form>\n</Layout>\n',
        "functions/contact.ts": "export async function onRequestPost({ request }) {\n"
        "  return new Response(null, { status: 204 });\n}\n",
    },
    "planner": {
        "README.md": "# Planner\n\nFloor plans in the browser: walls, doors, furniture.\n",
        "package.json": '{\n  "name": "planner",\n  "private": true,\n  "scripts": {\n'
        '    "dev": "vite",\n    "test": "vitest run"\n  }\n}\n',
        "src/plan/walls.ts": "export interface Wall {\n  from: [number, number];\n"
        "  to: [number, number];\n}\n",
        "src/plan/drag.ts": "export function dragged(at: [number, number]) {\n  return at;\n}\n",
        "src/export/svg.ts": "export function svgOf(): string {\n  return '<svg/>';\n}\n",
    },
    "quotes": {
        "README.md": "# Quotes\n\nThe studio's quotes: rooms, materials, labour and VAT.\n",
        "pyproject.toml": '[project]\nname = "quotes"\nversion = "0.4.0"\n',
        "quotes/__init__.py": "",
        "quotes/tax.py": "VAT = 0.25\n",
    },
}

# What the chats wrote and nobody committed yet, on top of the files above.
CHANGED = {
    "website/src/components/ProjectGrid.astro": "---\nimport { projects } from '../data/projects';"
    "\nconst room = Astro.url.searchParams.get('room');\n---\n<ul class=\"grid\">\n"
    "  {projects.filter((p) => !room || p.room === room).map((p) => (\n"
    "    <li><a href={`/work/${p.slug}`}>{p.title}</a></li>\n  ))}\n</ul>\n",
    "website/src/data/projects.ts": "export const projects = [\n  { slug: 'villa-lovran', title: "
    "'Villa Lovran', room: 'living', year: 2026 },\n  { slug: 'hotel-obala', title: 'Hotel "
    "Obala, lobby', room: 'hospitality', year: 2026 },\n  { slug: 'stan-tresnjevka', title: "
    "'Flat in Trešnjevka', room: 'kitchen', year: 2025 },\n];\n",
    "website/src/pages/work.astro": "---\nimport Layout from '../layouts/Layout.astro';\n"
    "import ProjectGrid from '../components/ProjectGrid.astro';\n---\n<Layout title=\"Work\">\n"
    "  <h1>Work</h1>\n  <ProjectGrid />\n</Layout>\n",
    "website/src/pages/work/villa-lovran.astro": "---\nimport Layout from "
    "'../../layouts/Layout.astro';\nimport BeforeAfter from '../../components/BeforeAfter.astro';"
    '\n---\n<Layout title="Villa Lovran">\n  <h1>Villa Lovran</h1>\n  <BeforeAfter />\n'
    "</Layout>\n",
    "website/src/components/BeforeAfter.astro": '<div class="before-after">\n  <input type="range"'
    ' min="0" max="100" value="50" />\n</div>\n',
    "planner/src/plan/snap.ts": "import type { Wall } from './walls';\n\nexport const REACH = 0.1;"
    "\n\nexport function snapped(at: [number, number], walls: Wall[]) {\n  return at;\n}\n",
    "planner/src/plan/drag.ts": "import { snapped } from './snap';\n\nexport function dragged(at: "
    "[number, number]) {\n  return snapped(at, []);\n}\n",
    "planner/src/export/pdf.ts": "export const A3 = { width: 420, height: 297 };\n",
}

MEMORY = {
    "website": {
        "MEMORY.md": "# Memory: website\n\n"
        "- [Deploy](project_deploy.md) — every push to main deploys; previews per branch\n"
        "- [Photos](feedback_photos.md) — client photos only from content/, never hotlinked\n",
        "project_deploy.md": "---\nname: project-deploy\ndescription: every push to main deploys; "
        "previews per branch\nmetadata:\n  type: project\n---\n\nEvery push to main deploys the "
        "site; each branch gets a preview address.\n",
        "feedback_photos.md": "---\nname: feedback-photos\ndescription: client photos only from "
        "content/, never hotlinked\nmetadata:\n  type: feedback\n---\n\nPhotos of clients' homes "
        "come only from `content/`, resized at build.\n\n**Why:** clients agreed to these "
        "photos and no others.\n**How to apply:** never link an image from elsewhere.\n",
    },
    "planner": {
        "MEMORY.md": "# Memory: planner\n\n"
        "- [Units](project_units.md) — the model keeps metres; centimetres only on screen\n",
        "project_units.md": "---\nname: project-units\ndescription: the model keeps metres; "
        "centimetres only on screen\nmetadata:\n  type: project\n---\n\nThe plan's model keeps "
        "every length in metres; the interface shows centimetres.\n",
    },
}

INSTRUCTIONS = (
    "# Sarah's instructions\n\n- Explain changes briefly, in English.\n"
    "- Never push without being asked.\n- Tests for every change, run before saying done.\n"
)

PLAN_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plan Website</title>
<style>
:root { --ink: #1f2a2c; --muted: #5d6b6d; --line: #d9dfdc; --paper: #fbfaf7; --done: #3f7d58;
  --doing: #2f6b6e; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --ink: #e8eeec; --muted: #a3b1b0; --line: #34403f;
  --paper: #161d1e; --done: #8fc4a0; --doing: #7fb5b3; } }
body { margin: 0; padding: 24px 16px; background: var(--paper); color: var(--ink);
  font: 15px/1.5 system-ui, sans-serif; }
main { max-width: 760px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 16px; }
li { padding: 8px 0; border-bottom: 1px solid var(--line); list-style: none; }
ul { padding: 0; }
b { display: inline-block; min-width: 84px; font-size: 13px; color: var(--muted); }
.done { color: var(--done); } .doing { color: var(--doing); }
</style>
</head>
<body>
<main>
<h1>Plan Website</h1>
<ul>
<li><b class="done">done</b> Contact form without spam</li>
<li><b class="doing">working</b> Portfolio grid with filters</li>
<li><b class="doing">working</b> Case study: Villa Lovran</li>
<li><b>next</b> Journal: three posts from the Hotel Obala site</li>
<li><b>next</b> Croatian and English side by side</li>
</ul>
</main>
</body>
</html>
"""

# The projects' share of the work on a working day, and how often each was worked on.
WORKED = (("website", 0.75, (40, 190)), ("planner", 0.55, (30, 160)), ("quotes", 0.3, (20, 90)))
WORKED_DAYS = 80
# The chats of the weeks before, by project, each day's titled by one of them.
TITLES = {
    "website": (
        "Gallery images in AVIF",
        "Studio page in Croatian",
        "Faster first load",
        "Project cards on the phone",
        "Sitemap and redirects",
    ),
    "planner": (
        "Undo across rooms",
        "Door swing on the plan",
        "Measure tool",
        "Import a DWG outline",
        "Room areas while drawing",
    ),
    "quotes": ("Discount per item", "Clients from the address book", "Quote numbering"),
}
# The share of each project's hours on each model.
MODEL_SHARES = {
    "website": ((OPUS, 0.8), (SONNET, 1.0)),
    "planner": ((OPUS, 0.55), (SONNET, 1.0)),
    "quotes": ((OPUS, 0.15), (SONNET, 1.0)),
}
# What a minute of an agent at work takes, roughly: its turns and each turn's tokens.
TURNS_PER_MINUTE = 1.4
PER_TURN = {"input": 8, "output": 420, "cache_read": 68_000, "cache_write": 2_600}
# The plan's windows as the workspace measured them, and the share of each its fullest one took.
SESSION = timedelta(hours=5)
WEEK = timedelta(days=7)
FULLEST = {"session": 88, "week": 82}
# A chat waiting to start each morning before the studio opens.
MORNING = (
    "Check every page of the site for broken links and images over 400 kB, and list them by "
    "page; change nothing."
)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _usage(chat: Chat, share: float) -> dict:
    whole = int(chat.context * share)
    return {
        "input_tokens": 6,
        "cache_creation_input_tokens": 1_200,
        "cache_read_input_tokens": max(0, whole - 2_406),
        "output_tokens": 1_200,
    }


def _transcript(chat: Chat, now: datetime) -> tuple[list[dict], datetime]:
    lines: list[dict] = []
    common = {"sessionId": chat.id, "cwd": chat.folder, "isSidechain": False}
    last = now
    for number, turn in enumerate(chat.turns, 1):
        at = now - timedelta(minutes=turn.ago)
        share = number / len(chat.turns)
        lines.append(
            {
                **common,
                "type": "user",
                "timestamp": _stamp(at),
                "message": {"role": "user", "content": turn.said},
            }
        )
        step = timedelta(minutes=turn.took) / (len(turn.tools) + 1)
        for place, (name, given) in enumerate(turn.tools, 1):
            moment = at + step * place
            lines.append(
                {
                    **common,
                    "type": "assistant",
                    "timestamp": _stamp(moment),
                    "message": {
                        "role": "assistant",
                        "model": chat.model,
                        "content": [
                            {
                                "type": "tool_use",
                                "id": f"toolu_{number}_{place}",
                                "name": name,
                                "input": given,
                            }
                        ],
                        "usage": _usage(chat, share * 0.95),
                    },
                }
            )
            last = moment
        if turn.answer:
            moment = at + timedelta(minutes=turn.took)
            lines.append(
                {
                    **common,
                    "type": "assistant",
                    "timestamp": _stamp(moment),
                    "message": {
                        "role": "assistant",
                        "model": chat.model,
                        "content": [{"type": "text", "text": turn.answer}],
                        "usage": _usage(chat, share),
                    },
                }
            )
            last = moment
    lines.append({"type": "ai-title", "aiTitle": chat.title, "sessionId": chat.id})
    return lines, min(last, now)


def _namespace(folder: str) -> str:
    return "".join(each if each.isalnum() else "-" for each in folder)


def _write(path: Path, text: str, moment: datetime | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if moment:
        os.utime(path, (moment.timestamp(), moment.timestamp()))


def _json(path: Path, value) -> None:
    _write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _home(root: Path, now: datetime) -> None:
    agent = root / ".claude"
    for chat in CHATS:
        lines, last = _transcript(chat, now)
        file = agent / "projects" / _namespace(chat.folder) / f"{chat.id}.jsonl"
        _write(
            file,
            "".join(
                json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n" for line in lines
            ),
            last,
        )
    by_key = {chat.key: chat for chat in CHATS}
    begun = now - timedelta(minutes=178)
    _json(
        agent / "ponistra-rounds" / f"website-{begun:%Y%m%d-%H%M}.json",
        {
            "round": f"website-{begun:%Y%m%d-%H%M}",
            "folder": f"{HOME}/website",
            "title": "Spring portfolio",
            "coordinator": by_key["website-coordinator"].id,
            "created": _stamp(begun),
            "started": _stamp(begun + timedelta(minutes=8)),
            "named": _stamp(begun + timedelta(minutes=8)),
            "auto": True,
            "chats": [
                {"prompt": prompt, "sessionId": by_key[f"website-{key}"].id}
                for key, prompt in ROUND_TASKS
            ],
        },
    )
    divided = now - timedelta(minutes=20)
    _json(
        agent / "ponistra-rounds" / f"quotes-{divided:%Y%m%d-%H%M}.json",
        {
            "round": f"quotes-{divided:%Y%m%d-%H%M}",
            "folder": f"{HOME}/quotes",
            "title": "Quotes for spring",
            "coordinator": by_key["quotes-coordinator"].id,
            "created": _stamp(divided),
            "started": None,
            "named": _stamp(divided),
            "auto": True,
            "chats": [{"prompt": prompt} for prompt in QUOTE_TASKS],
            "when": {"on": "reset", "pause": 90, "since": _stamp(divided)},
        },
    )
    offline = now - timedelta(minutes=152)
    _json(
        agent / "ponistra-rounds" / f"planner-{offline:%Y%m%d-%H%M}.json",
        {
            "round": f"planner-{offline:%Y%m%d-%H%M}",
            "folder": f"{HOME}/planner",
            "title": "Offline plans",
            "coordinator": by_key["planner-coordinator"].id,
            "created": _stamp(offline),
            "started": _stamp(offline + timedelta(minutes=6)),
            "named": _stamp(offline + timedelta(minutes=6)),
            "auto": True,
            "chats": [
                {"prompt": prompt, "sessionId": by_key[f"planner-{key}"].id}
                for key, prompt in PLANNER_TASKS
            ],
            "done": _stamp(now - timedelta(minutes=5)),
        },
    )
    heard = {
        "website-spam": {
            "event": "stop",
            "at": _stamp(now - timedelta(minutes=139)),
            "message": None,
        },
        "website-lovran": {
            "event": "notification",
            "at": _stamp(now - timedelta(minutes=140)),
            "message": "Claude needs your permission to use Bash",
        },
        "planner-coordinator": {
            "event": "stop",
            "at": _stamp(now - timedelta(minutes=6)),
            "message": None,
        },
        "website-coordinator": {
            "event": "stop",
            "at": _stamp(now - timedelta(minutes=20)),
            "message": None,
        },
    }
    for key, said in heard.items():
        _json(agent / "ponistra-heard" / f"{by_key[key].id}.json", said)
    for project, files in MEMORY.items():
        for name, text in files.items():
            _write(agent / "projects" / _namespace(f"{HOME}/{project}") / "memory" / name, text)
    _write(agent / "CLAUDE.md", INSTRUCTIONS)
    for project, files in FILES.items():
        for name, text in files.items():
            _write(root / project / name, text)
    _json(
        root / MANIFEST,
        {
            "home": HOME,
            "projects": list(FILES),
            "committed": _stamp(now - timedelta(days=3)),
            "changed": {f"{HOME}/{name}": text for name, text in CHANGED.items()},
            "running": [
                {
                    "session": chat.id,
                    "cwd": chat.folder,
                    "status": chat.status,
                    "waitingFor": chat.waiting_for,
                    "name": chat.name,
                    "since": int(
                        (now - timedelta(minutes=chat.turns[0].ago + 1)).timestamp() * 1000
                    ),
                }
                for chat in CHATS
                if chat.status
            ],
            "usage": USAGE,
            "models": MODELS,
        },
    )


def _worked(now: datetime) -> list[worked.Spent]:
    """The time worked before the chats on the disk began and the tokens it took, as the workspace
    would have told them."""
    chance = random.Random(7)
    today = timezone.localtime(now).date()
    taken: list[worked.Spent] = []
    for back in range(WORKED_DAYS, 0, -1):
        day = today - timedelta(days=back)
        if day.weekday() >= 5:
            continue
        start = timezone.make_aware(datetime.combine(day, datetime.min.time())) + timedelta(hours=9)
        for project, share, (shortest, longest) in WORKED:
            if chance.random() > share:
                continue
            began = start + timedelta(minutes=chance.randint(0, 300))
            spans = []
            for _ in range(chance.randint(1, 3)):
                ended = began + timedelta(minutes=chance.randint(shortest, longest) // 2)
                spans.append((began, ended))
                began = ended + timedelta(minutes=chance.randint(20, 90))
            session = str(uuid.uuid5(IDS, f"{project}-{day}"))
            spent = _spent(spans, MODEL_SHARES[project], chance)
            taken += spent
            worked.kept(
                _namespace(f"{HOME}/{project}"),
                session,
                project,
                None,
                spans,
                worked.Found(
                    chat=session,
                    round=f"{project}-{day:%Y%m%d}-0900" if chance.random() < 0.3 else "",
                    title=chance.choice(TITLES[project]),
                    spent=spent,
                ),
            )
    return taken


def _spent(spans, shares, chance: random.Random) -> list[worked.Spent]:
    """The tokens of each hour the spans touch, on a model picked by the project's shares."""
    minutes: dict[datetime, float] = {}
    for began, ended in spans:
        moment = began
        while moment < ended:
            hour = moment.replace(minute=0, second=0, microsecond=0)
            step = min(ended, hour + timedelta(hours=1)) - moment
            minutes[hour] = minutes.get(hour, 0) + step.total_seconds() / 60
            moment += step
    spent = []
    for hour, worked_for in sorted(minutes.items()):
        pick = chance.random()
        model = next(name for name, upto in shares if pick <= upto)
        turns = max(1, round(worked_for * TURNS_PER_MINUTE * chance.uniform(0.7, 1.3)))
        spent.append(
            worked.Spent(
                hour=hour.astimezone(UTC),
                model=model,
                turns=turns,
                **{
                    name: int(each * turns * chance.uniform(0.8, 1.2))
                    for name, each in PER_TURN.items()
                },
            )
        )
    return spent


def _worth(each: worked.Spent) -> float:
    price = PRICES[each.model]
    return float(
        (
            each.input * price.input
            + each.output * price.output
            + each.cache_read * price.cached
            + each.cache_write * price.input * CACHE_WRITE
        )
        / 1_000_000
    )


def _limits(now: datetime, taken: list[worked.Spent]) -> None:
    """The plan's five-hour and weekly windows as the workspace would have measured them each hour
    of the working day, filled by the worth of the tokens taken in each and ending as the agent
    reports today's: the week on the same weekday and hour."""
    worth = sorted((each.hour, _worth(each)) for each in taken)
    resets = now + timedelta(minutes=USAGE["seven_day"]["resets_in"])
    week_ends = resets
    while week_ends - WEEK > worth[0][0]:
        week_ends -= WEEK
    sessions: list[tuple[datetime, float]] = []
    for hour, each in worth:
        if not sessions or hour >= sessions[-1][0] + SESSION:
            sessions.append((hour, 0.0))
        sessions[-1] = (sessions[-1][0], sessions[-1][1] + each)
    weeks: dict[datetime, float] = {}
    for hour, each in worth:
        ends = week_ends
        while hour >= ends:
            ends += WEEK
        weeks[ends] = weeks.get(ends, 0.0) + each
    session_rate = FULLEST["session"] / max(total for _, total in sessions)
    # The week under way stays below what the agent reports of it today.
    under_way = weeks.get(resets)
    week_rate = min(
        FULLEST["week"] / max(weeks.values()),
        (USAGE["seven_day"]["utilization"] - 6) / under_way if under_way else 1e9,
    )
    rows = []
    first = timezone.localtime(worth[0][0]).replace(hour=0, minute=0, second=0, microsecond=0)
    moment = first
    yesterday = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    while moment < yesterday:
        local = timezone.localtime(moment)
        if 8 <= local.hour <= 20 and local.weekday() < 5:
            ends = week_ends
            while moment >= ends:
                ends += WEEK
            in_week = sum(each for hour, each in worth if ends - WEEK <= hour < moment)
            began = next(
                (start for start, _ in reversed(sessions) if start <= moment < start + SESSION),
                None,
            )
            in_session = (
                sum(each for hour, each in worth if began <= hour < moment) if began else 0.0
            )
            rows.append(
                Limits(
                    at=moment,
                    windows=[
                        {
                            "kind": "session",
                            "name": None,
                            "percent": round(in_session * session_rate),
                            "resets": (began + SESSION if began else moment + SESSION).isoformat(),
                        },
                        {
                            "kind": "week",
                            "name": None,
                            "percent": round(in_week * week_rate),
                            "resets": ends.isoformat(),
                        },
                    ],
                )
            )
        moment += timedelta(hours=1)
    Limits.objects.bulk_create(rows)


def _waiting(root: Path, now: datetime) -> None:
    """A chat that starts each weekday morning before the studio opens, waiting for the next."""
    zone = timezone.get_current_timezone()
    tomorrow = timezone.localtime(now).date() + timedelta(days=1)
    at = datetime.combine(tomorrow, datetime.min.time(), zone) + timedelta(hours=7)
    when = {"on": "time", "pause": 80, "at": at.astimezone(UTC).isoformat(), "every": "day"}
    folder = f"{HOME}/website"
    command = Command.objects.create(
        kind=Command.Kind.CHAT,
        folder=folder,
        text=MORNING,
        when=when,
        state=Command.State.WAITING,
    )
    asked = now - timedelta(days=2, hours=3)
    _json(
        root / ".claude" / "ponistra-commands" / f"{command.pk}.json",
        {
            "id": command.pk,
            "kind": "chat",
            "folder": folder,
            "round": None,
            "session": None,
            "text": MORNING,
            "images": [],
            "label": None,
            "auto": False,
            "state": "waiting",
            "error": None,
            "created": _stamp(asked),
            "at": _stamp(asked),
            "when": {**when, "at": _stamp(at), "since": _stamp(asked)},
            "sessions": [],
            "paused": [],
        },
    )


def _plan(seeded: Seeded) -> None:
    title = "Plan Website"
    node = created(
        boards_place.group_of(seeded.user, "Website"),
        Node.Kind.FILE,
        title,
        boards.page(PLAN_PAGE),
        seeded.user,
        "html",
    )
    boards.begun(node, seeded.user, "")


def seed(seeded: Seeded) -> None:
    if seeded.user.email.lower() != settings.WORKSPACE:
        return
    root = settings.WORKSPACE_ROOT
    if any(root.iterdir()):
        raise RuntimeError(
            f"{root} holds a workspace already; the demo's is seeded into an empty one"
        )
    now = timezone.now()
    _home(root, now)
    _waiting(root, now)
    _limits(now, _worked(now))
    _plan(seeded)
