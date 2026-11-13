# Agent's memory

An overview of the memory Claude Code keeps per project in the code workspace, with proposed corrections you accept or reject and a history from which every change is taken back.

## How to use it

### Overview of the memory

1. On the module rail press {t:rail.projects}.
2. Press {t:workspace.view.memory} at the top of the page.
3. Under {t:memory.stores} stands each project's store. Press a store's row to see its findings, grouped by kind.

### A proposal for the memory

1. While proposals wait, their number stands beside {t:workspace.view.memory} atop the {t:rail.projects} page. Press {t:workspace.view.memory}.
2. Under {t:memory.proposals} each proposal shows the file, the project, the kind, the reason when there is one and the change: deleted lines struck through, added ones highlighted. {t:memory.removes} means the proposal deletes the whole file, and {t:memory.creates} that it creates it. When nothing waits, it says {t:memory.none}
3. Press {t:memory.accept} to have the change written, or {t:memory.reject} to discard it.

On a phone or computer with notifications turned on, the buttons {t:workspace.yes} and {t:workspace.no} in the notification of a proposal do the same.

### Taking a change back

1. On the {t:workspace.view.memory} tab find the change under {t:memory.history}.
2. Press {t:memory.revert}. The file returns to what it was before the change, and the row then says {t:memory.reverted}.

### Analysing the memory

1. On the {t:workspace.view.memory} tab press {t:memory.analyse} for every store, or {t:memory.analyseStore} in one store's row.
2. The workspace starts a new conversation with the agent, and the tab says {t:memory.analysing} The conversation also shows in the list of the {t:rail.projects} page.
3. The analysis's proposals arrive under {t:memory.proposals} as the agent writes them.

### Analysing the proposals

1. While proposals wait, press {t:memory.review} on the {t:workspace.view.memory} tab.
2. An agent in a new conversation reads the open proposals and sorts them into groups, each with a title, a reason and its advice: {t:memory.advice.accept}, {t:memory.advice.reject} or {t:memory.advice.look}. A notification arrives once the groups are ready.
3. Under {t:memory.proposals}, accept or reject all of a group's proposals at once with the button beside it; the button carries their number, and the advised action stands out. Proposals whose line changed meanwhile go stale, and the group says how many. {t:memory.showProposals} opens the group's proposals, which can still be decided one by one.
4. Proposals the analysis left out stand under {t:memory.unsorted}.

### The nightly pass

1. On the {t:workspace.view.memory} tab turn on {t:memory.nightly}.
2. Every night at 4 o'clock the memory is read again, and what changed since the last analysis is analysed as with {t:memory.analyse}. Turning the box off stops the pass.

## How it works

The workspace reads each memory folder of its projects, `~/.claude/projects/<project>/memory/`, and tells Ponistra as soon as a file in one changes; the tab then refreshes by itself, on every device. For each store it shows {t:memory.files} (the number of files), {t:memory.indexLines} (the lines of the `MEMORY.md` index, which Claude Code loads into every session of that project), {t:memory.tokens} (how many tokens that index adds to every session, estimated at 4 bytes a token) and {t:memory.findings}. An index longer than 200 lines is marked with {t:memory.cut}

The findings are mechanical, without a model:

- {t:memory.finding.orphan}: a file the index does not list, so a session does not find it.
- {t:memory.finding.dangling}: an index line pointing to a file that does not exist.
- {t:memory.finding.link}: a link `[[name]]` to a memory that does not exist.
- {t:memory.finding.frontmatter}: the header lacks `name`, `description` or `type`.
- {t:memory.finding.oversize}: a file larger than 25,000 bytes, a rule or reference larger than 8,000.
- {t:memory.finding.long}: the index has more than 145 lines or 26,000 bytes.
- {t:memory.finding.stale}: a file or a name in the code that the memory names and the project's repository no longer has.
- {t:memory.finding.unreadable}: the file cannot be read as text.

Mechanical proposals come from the same reading:

- {t:memory.kind.state}: a dated line saying work is uncommitted or unpushed while git already records the files it names as committed; the proposal writes the commit and the release that carries it, or that it was pushed.
- {t:memory.kind.path}: a path that no longer exists is replaced by the only file of the same name in the same folders.
- {t:memory.kind.time}: a time in UTC on a line that names a day becomes that day's local time (CET/CEST); a time inside a code mark stays, and so does a time without a day, as it recurs and its local hour moves with summer time.
- {t:memory.kind.link}: a link `[[name]]` is corrected to an existing memory's name.
- {t:memory.kind.index}: index lines without a file are deleted, and lines are added for rules and references the index does not list.
- {t:memory.kind.frontmatter}: the header is completed with a name and a type.

{t:memory.kind.session} is a proposal the agent wrote. An analysis hands the agent in the workspace only the files changed since the last analysis, at most 80 at once and the rest in the next. The agent looks for duplicates within a store, contradictions between memories and with the project's `CLAUDE.md`, rules repeated in three or more stores, which it proposes once for the global `~/.claude/CLAUDE.md`, and index lines longer than needed. It changes no file itself: it sends each proposal with the `propose_memory` tool through Ponistra's MCP, with a reason of one sentence. The conversation runs on the Claude Code subscription in the workspace, not on Ponistra's AI.

A proposal remembers the content of the file it was made from. {t:memory.accept} writes the change only while the file is still exactly that; the write is whole, so a session never reads a half-written file. If the file changed meanwhile on other lines, for instance by accepting another proposal for the same file, the change is written over that one. If the same line changed, the proposal goes stale and leaves the list, and a mechanical proposal is made anew from the new content. The same holds for {t:memory.revert}. A rejected mechanical proposal is not offered again until the file changes. The history shows the last 30 written and reverted changes.

The owner gets a push notification for every new proposal: of one with the buttons {t:workspace.yes} and {t:workspace.no}, of several with their number. {t:memory.review} gives the agent only an excerpt of each proposal (the changed words with a little text around them) through the `memory_proposals` tool, and it sends the groups back with `advise_memory`; a new analysis replaces the groups of the one before. A group is accepted proposal by proposal in the order they were made, so two proposals for the same file are written one over the other. The notification opens the {t:workspace.view.memory} tab.

## Limits

The tab exists only for the owner of the code workspace, and the `propose_memory`, `memory_proposals` and `advise_memory` tools accept only their agent. Ponistra reads and writes the memory only through the workspace, so without it the tab reports an error.

- {t:error.not_the_owner} Only the user the workspace is assigned to sees the memory.
- {t:error.workspace_unreachable} The workspace is not running or its token differs from the installation's.
- {t:error.memory_changed} The file changed since the proposal was made or the change was written; read the new proposal.
- {t:error.memory_decided} The proposal was already decided, on another device or from a notification for instance.
- {t:error.memory_analysed} No file changed since the last analysis.
- {t:error.memory_nothing_waiting} No proposals are open to analyse.

The mechanical findings do not understand the content: a name that is old on purpose, in a record of history for instance, is still reported as {t:memory.finding.stale}.

## Related

- [Projects](help:agents/projects)
- [Connecting an outside agent](help:agents/connecting)
- [Notifications](help:account/notifications)
