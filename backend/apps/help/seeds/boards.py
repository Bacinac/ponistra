"""A board the account keeps for the studio's projects: a page that draws what its data holds."""

from apps.documents import board_data, boards, boards_place
from apps.documents.models import Node
from apps.documents.views import created
from apps.search import extraction

from .company import Seeded

PAGE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --ink: #1f2a2c; --muted: #5d6b6d; --line: #d9dfdc; --paper: #fbfaf7; --accent: #2f6b6e;
  --done: #3f7d58; --late: #b5654a; color-scheme: light dark; }}
@media (prefers-color-scheme: dark) {{ :root {{ --ink: #e8eeec; --muted: #a3b1b0; --line: #34403f;
  --paper: #161d1e; --accent: #7fb5b3; --done: #8fc4a0; --late: #e39a80; }} }}
body {{ margin: 0; padding: 24px 16px; background: var(--paper); color: var(--ink);
  font: 15px/1.5 system-ui, sans-serif; }}
main {{ max-width: 880px; margin: 0 auto; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
p {{ color: var(--muted); margin: 0 0 20px; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); }}
th {{ font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }}
.stage {{ font-weight: 600; color: var(--accent); }}
.stage.done {{ color: var(--done); }} .stage.late {{ color: var(--late); }}
</style>
</head>
<body>
<main>
<h1>{title}</h1>
<p>{intro}</p>
<table>
<thead><tr><th>{project}</th><th>{client}</th><th>{lead}</th><th>{stage}</th><th>{due}</th></tr></thead>
<tbody id="rows"></tbody>
</table>
</main>
<script src="/api/boards/runtime.js"></script>
<script>
const rows = document.getElementById('rows');
function draw(snapshot) {{
  rows.replaceChildren(...snapshot.docs
    .map((doc) => doc.data())
    .sort((a, b) => a.order - b.order)
    .map((item) => {{
      const row = document.createElement('tr');
      for (const value of [item.name, item.client, item.lead, item.stage, item.due]) {{
        const cell = document.createElement('td');
        cell.textContent = value;
        row.append(cell);
      }}
      row.children[3].className = 'stage ' + (item.state || '');
      return row;
    }}));
}}
if (window.ponistra && window.ponistra.db) {{
  window.ponistra.db.collection('projects').onSnapshot(draw);
}}
</script>
</body>
</html>
"""

PROJECTS = (
    (
        "meridian",
        "Meridian",
        "Meridian d.o.o.",
        "klara",
        ("Ponuda poslana", "Proposal sent"),
        "",
        ("12. 1. 2027.", "12 Jan 2027"),
    ),
    (
        "apex",
        "Apex",
        "Apex d.o.o.",
        "tomislav",
        ("Predano", "Handed over"),
        "done",
        ("3. 10. 2026.", "3 Oct 2026"),
    ),
    (
        "vrt",
        ("Vrtić Lastavica", "Lastavica kindergarten"),
        "Grad Zagreb",
        "ana",
        ("Projekt", "Design"),
        "",
        ("20. 2. 2027.", "20 Feb 2027"),
    ),
    (
        "hotel",
        ("Hotel Obala, lobi", "Hotel Obala, lobby"),
        "Obala d.d.",
        "elena",
        ("Kasni nabava", "Purchase late"),
        "late",
        ("15. 12. 2026.", "15 Dec 2026"),
    ),
)


def seed(seeded: Seeded) -> None:
    say, user, company = seeded.say, seeded.user, seeded.company
    title = say("Projekti studija", "Studio projects")
    html = PAGE.format(
        lang=seeded.language,
        title=title,
        intro=say(
            "Stanje svih projekata Lipa Studija na jednom mjestu.",
            "Where each of Lipa Studio's projects stands, in one place.",
        ),
        project=say("Projekt", "Project"),
        client=say("Klijent", "Client"),
        lead=say("Vodi", "Lead"),
        stage=say("Faza", "Stage"),
        due=say("Rok", "Due"),
    )
    blob = boards.page(html)
    place = boards_place.group_of(user, "Lipa Studio")
    node = created(place, Node.Kind.FILE, title, blob, user, "html")
    boards.begun(node, user, "")
    lead = lambda key: user.get_full_name() if key == "klara" else company.name(key)  # noqa: E731
    board_data.written(
        node,
        [
            {
                "op": "set",
                "collection": "projects",
                "key": key,
                "data": {
                    "order": order,
                    "name": say(*name) if isinstance(name, tuple) else name,
                    "client": client,
                    "lead": lead(who),
                    "stage": say(*stage),
                    "state": state,
                    "due": say(*due),
                },
            }
            for order, (key, name, client, who, stage, state, due) in enumerate(PROJECTS)
        ],
        user,
    )
    extraction.wake()
