# Projects

The desk of your code workspace: projects with their rounds and chats, a conversation with the agent right on the page, and the activity of everything you asked of the workspace.

## How to use it

### Signing in to Claude Code

The chats run Claude Code in the workspace, which signs in once, with a Claude subscription or a Console account.

1. Open {t:rail.projects}: on a computer on the bar of modules, on a phone from the account menu.
2. Press the {t:workspace.terminal.open} icon right of {t:workspace.general}.
3. Type `claude auth login` and press Enter.
4. Open the address the terminal prints, sign in and copy the code you are given.
5. Paste the code into the terminal and press Enter.

### A new chat

1. On the bar of modules press {t:rail.projects}.
2. Find the project. {t:workspace.general} is the workspace as a whole, for chats that belong to no single project.
3. Press the {t:workspace.newChat} icon right of the project's name (its name shows when the mouse rests on it).
4. The form opens in the chat's place (on a phone in place of the list), the cursor already in its field. In the field {t:workspace.newChatText} type the first message, or press {t:speech.dictate} and say it. Images are added as in a message on the page.
5. Below the field stands the {t:workspace.model} the chat will start on, the one it would get anyway. To start it on another, press it and choose one; the chat answers on it from its first message, and a model chosen with {t:workspace.startWhen} waits with the command until it starts.
6. Press {t:workspace.startChat} or Enter, as in a message on the page; until the workspace answers, the button spins and another press sends nothing. The chat starts in the workspace and shows in the form's place; the editor does not open. To start it later, press {t:workspace.startWhen} (the section Starting on a condition).

### Back to a chat

1. On the {t:rail.projects} page find the chat under its project. Closed chats stand behind the project's name: press the name.
2. Press the title of a closed chat. It shows beside the list, as a chat in use does.
3. Send it a message and the workspace carries on with it. To carry on with it in the editor, press {t:workspace.openChat}.

### Talking to the agent on the page

1. On the {t:rail.projects} page press a chat. On a phone {t:workspace.view.chat} then opens (the buttons at the top switch between {t:workspace.view.overview} and {t:workspace.view.chat}, and the {t:workspace.view.more} menu beside them offers [{t:workspace.view.memory}](help:agents/memory), {t:workspace.view.hours}, [{t:workspace.view.spend}](help:agents/spend), the terminal and the files); on a computer the list stands in the left column, like the folders beside documents, and the chat to its right, until the {t:workspace.view.memory} button, far right in the row with {t:workspace.view.chat}, replaces it with the agent's memory. Each scrolls on its own, and the list is widened or narrowed by dragging the thin line between the list and the chat. Until you pick one, the coordinator of the latest round is shown.
2. In the field {t:workspace.say} type a message, or press {t:speech.dictate} and say it.
3. For an image, paste it into the field (Ctrl+V), drag it onto the field or press {t:workspace.addImage}. It shows small below the field; {t:workspace.removeImage} takes it off before sending. A right click in the field pastes the clipboard's text where the caret stands, or its image when it holds no text. If the browser does not let the clipboard be read, below the field it says: {t:error.clipboard_refused}
4. Press {t:workspace.send} or Enter; Shift+Enter starts a new line, and on a phone Enter starts a new line, so the button sends. Until the workspace answers, the button spins and another press sends nothing. For frequent words press {t:workspace.quick.catchup}, {t:workspace.quick.continue} or {t:workspace.quick.handoff}; each is sent at once. A message you send stands at the foot of the conversation at once. Until the agent reads it, it is framed and below it says {t:workspace.unread}; the agent reads it when it finishes the step it is on, and it then becomes part of the conversation. Until then {t:workspace.withdraw} (the X in the message) puts it back into the field, before what you had begun to write, so that you can join it to a new one and send it once; images sent with it do not come back. If the agent took it in the meantime, below it says {t:error.already_read}
5. For the text of the agent's answer press {t:workspace.copy} below it; a code block has a {t:workspace.copy} of its own in its top right corner, which copies the code alone. The button shows {t:workspace.copied} for a moment, or {t:workspace.copyFailed} if the browser does not allow writing to the clipboard.
6. The {t:workspace.model} the chat runs on stands beside {t:workspace.send}. Press it and choose another; it holds from the next answer. If the chat runs in the editor, the change waits until it is idle, and the workspace then takes it over. The models offered are those Claude Code in the workspace offers, and the model stays when the workspace restarts.
7. While the agent works or waits for you, {t:workspace.stop} stands beside {t:workspace.send}. Press it and the agent breaks off what it does, as Esc does in the editor; a permission it waited for is refused, and the chat stays open for your next message. A chat working in the editor is stopped there, so the button is disabled.
8. For the whole chat in the editor press {t:workspace.openChat}. While the agent works or waits for you, the button is disabled.

### Answering a chat that waits

1. On the {t:rail.projects} page, while a chat waits, {t:workspace.waitingForYou} stands at the top of the list (on a phone in {t:workspace.view.overview}, the number beside that button saying how many chats wait).
2. There stands every chat waiting for your answer or permission, with what it asks.
3. To a permission, press {t:workspace.yes} or {t:workspace.no}.
4. A chat asking you questions with offered answers has no buttons there, but a red mark with the number of its questions (Questions for you: 2). Click the chat or the mark and the questions appear in the conversation, each on its own: a heading, the question and a button for each offered answer, its description below it.
5. Press an answer to each question. Where more than one answer may be chosen, each press turns one on or off. Instead of an offered answer you can type your own into the field {t:workspace.ownAnswer} below the question.
6. Once every question has an answer, press {t:workspace.sendAnswers}.

The same {t:workspace.yes} and {t:workspace.no}, or the same questions, also stand in the conversation when a waiting chat is selected.

### The chat's menu

1. On the {t:rail.projects} page right-click any chat, or press it long.
2. Choose what it needs:
   - {t:workspace.openChat} opens the chat in the editor. It is disabled while the agent works or waits for you.
   - {t:tree.rename} gives the chat a new name of up to 100 characters; the editor and the list of sessions show the same name.
   - {t:workspace.moveUnder} moves the chat under the coordinator of another round of the same project.
   - {t:workspace.auto}, in the coordinator's menu, turns on and off whether the coordinator brings the round's work together by itself.
   - {t:workspace.close} stops a chat in use, in the workspace and in the editor. A chat of a round stays in the round; any other chat that does not run leaves the project's list and is archived by itself, wherever it was stopped.
   - {t:workspace.archive} takes the chat off the project's list; one in use is closed first, as with {t:workspace.close}. The editor closes a new tab of an archived chat as soon as it opens, so a window that loads or reconnects does not bring it back. An archived chat comes back to the list only once you write to it in a tab already open.

### A new round

1. On the {t:rail.projects} page press the {t:workspace.newRound} icon right of the project's name.
2. The form opens in the chat's place. In the field {t:workspace.newRoundText} type what the round should do, or press {t:speech.dictate} below the field and say it. The field may stay empty: the coordinator then takes the next steps from the project's plan. The coordinator's {t:workspace.model} is chosen below the field, as in a new chat.
3. Press {t:workspace.openRound} or Enter. The workspace starts a coordinator with the message “nastavi: …” and shows it in the form's place; the editor does not open.
4. The coordinator divides the work into chats. The round appears on the page, and beside each chat not yet sent stands its task: press the chat to read it.

### A round of chats

1. On the {t:rail.projects} page find the round under its project. The round begins with the row of {t:workspace.coordinator}, the chat that opened the round and bears its name, and below the coordinator, indented, stand the round's chats.
2. If the chats have not started yet, press {t:workspace.start}. The workspace starts each chat of the round with the task written for it.
3. Press a chat of the round to read it in the conversation on the page. {t:workspace.openChat} opens it in the editor.
4. When every chat of the round is done, the coordinator brings the round's work together by itself as soon as it is idle, while {t:workspace.auto} is on in its menu. With it off, write “objedini” to the coordinator when you want it.

5. Once the work is brought together, the check found it green and no push has carried it yet, {t:workspace.push} stands below the coordinator's row instead; when the coordinator has already closed the round, the button stands below its row in the project's list of chats. Press it. The coordinator then pushes the work; a release to production still needs your explicit word in the chat.
6. Once the coordinator says everything is finished (consolidation, plan, memory and the push if you asked for it) and is idle, {t:workspace.close} stands below its row. Press it and the coordinator stops.

### Starting on a condition

1. On the {t:rail.projects} page press the clock ({t:workspace.startWhen}) beside {t:workspace.start} below the coordinator of a round not yet started, or {t:workspace.startWhen} beside {t:workspace.startChat} in the new chat form, once you have written the first message.
2. In the {t:workspace.when.on} field choose when:
   - {t:workspace.when.time}: a day and an hour. For a chat, the {t:workspace.when.repeat} field offers {t:workspace.when.once}, {t:workspace.when.daily} or {t:workspace.when.weekly}.
   - {t:workspace.when.reset}: when the plan's weekly limit resets.
   - {t:workspace.when.below}: when the five-hour window is below the percent in the {t:workspace.when.percent} field.
   - {t:workspace.when.round}: when the round you choose in the {t:workspace.when.which} field closes; offered while another round is open.
   - {t:workspace.when.red}: when the nightly run of all of that project's tests fails.
3. So that the work does not eat the week, turn on {t:workspace.when.pausing} and enter {t:workspace.when.pause}.
4. Press {t:workspace.when.set}. The round or the chat then waits below its project or coordinator, with the condition in words; {t:workspace.cancelWhen} calls it off.

### Moving to another round

1. On the {t:rail.projects} page drag a chat with the mouse onto a round of the same project and let it go. A frame around the round shows that it takes the chat. {t:workspace.moveUnder} in the chat's menu does the same, on a phone too.
2. The chat joins the round. If it was in another round, that round's coordinator is told the chat is no longer its own.
3. The chat and its new coordinator are told of the move as soon as they can read it: once they finish the step they are working on and do not wait for your answer. The chat tells the coordinator its steps and area, and the coordinator leads it like the others and includes it when consolidating.

A coordinator dragged onto another round brings its whole round along: its chats and the coordinator itself become chats of that round, and its round leaves the page. It hands the state of its round to the new coordinator in a message. No round takes a chat of another project, and nothing moves into or out of a round already sent its consolidation or {t:workspace.push} until it has carried it out.

### Restarting the workspace

1. On the {t:rail.projects} page press {t:workspace.restart} in the header.
2. In the dialog {t:workspace.restartTitle} confirm with {t:workspace.restart}. The button then reads {t:workspace.restarting}, and the page comes back once the workspace answers again.

### Projects beside your work in Ponistra

1. On a computer press {t:rail.projects} on the bar of modules, or pick that command in the search box.
2. The page opens in a window of its own without the bar of modules, placed as a meeting's: over the whole of the largest other screen when the computer has more than one and you allowed window management, otherwise over Ponistra's window. Go on working in Ponistra.

Going to {t:rail.projects} again brings that same window forward rather than opening another. {t:meeting.nextScreen} in the window's header moves it to the next screen and fills it, when the computer has more than one; this needs permission to manage windows in the site's settings. A narrow window has the buttons for the chat and the memory as on a phone, a wide one the list and the chat side by side, the list as wide as you drag its separator, as in Ponistra's tab. A notification of the workspace opens in that window while it is open. The window takes a new version of Ponistra once you put it out of sight, unless a terminal, an unsent message or an unsaved change to a file is open in it. If the browser does not allow a window of its own, the page opens in Ponistra's tab and says so; pop-ups are allowed in the browser's settings for the site, and the {t:workspace.beside} icon in the header then tries again. On a phone the page opens in the tab. The page can have a theme other than the rest of Ponistra's, in the tab and in its own window: {t:frame.theme.projects} in the account menu ([Theme and language](help:start/appearance)).

### Terminal

1. On the {t:rail.projects} page press the {t:workspace.terminal.open} icon to the right of the project's name.
2. If you have not confirmed who you are in the last 8 hours, confirm it.
3. The terminal opens in the chat's place, in the project's folder. Type commands as in any terminal; Ctrl+C stops a command. A right click pastes the clipboard's text, and when something in the terminal is selected, copies the selection.
4. The {t:workspace.view.terminal} button at the top (on a phone in the {t:workspace.view.more} menu) brings the terminal back while you look at a chat or the memory; a command in it keeps running meanwhile.
5. {t:workspace.terminal.close} at the right above the terminal closes it and ends the shell with everything started in it.

When the connection is lost, say while Ponistra updates, the network stalls or the phone sleeps, below the terminal it says {t:workspace.terminal.lost} The shell keeps running meanwhile, and as soon as the connection is back, the terminal shows everything it wrote in between. When the shell ends (the `exit` command), the terminal closes by itself; the {t:workspace.terminal.open} icon opens a new shell. If you open the same terminal on another device or in another window, it carries on there, and here it says {t:workspace.terminal.taken} {t:workspace.terminal.reopen} brings it back here. If the terminal cannot be opened, below it says: {t:workspace.terminal.unopened} {t:workspace.terminal.reopen} tries again.

### Files

1. On the {t:rail.projects} page press the {t:workspace.files.open} icon to the right of the project's name.
2. The files open in the chat's place: the tree of the project's folder on the left, the chosen file on the right. Folders stand before files; a click on a folder opens it below itself, another click closes it.
3. Press a file. Text opens in an editor with line numbers and colours by the kind of file; {k:Mod-f} searches it, {k:Mod-z} undoes a change.
4. Edit the text. Above it says {t:workspace.files.unsaved}.
5. Press {t:workspace.files.save} or {k:Mod-s}. Once the file is written, it says {t:workspace.files.saved}.
6. The {t:workspace.view.files} button at the top (on a phone in the {t:workspace.view.more} menu) brings the files back while you look at a chat or the terminal; unsaved changes stay meanwhile.
7. {t:workspace.files.close} at the right above the files closes them.

A file that is not text or is larger than 1 MB does not open in the editor: beside its size it says {t:workspace.files.binary} or {t:workspace.files.large} The {t:workspace.files.download} button downloads it. While no file is chosen, the right side says {t:workspace.files.none} A folder with nothing in it says in the tree {t:workspace.files.empty} On a phone the tree fills the screen; the chosen file takes its place, and the {t:workspace.files.back} arrow to the left of the project's name brings the tree back.

If you changed a file and then choose another, close the files or open them for another project, Ponistra asks {t:workspace.files.discard} with the note {t:workspace.files.discardBody} {t:workspace.files.discardConfirm} drops the changes, and cancelling keeps you in the file.

### Files on hosts

The same view of files opens folders on other machines the workspace reaches over SSH.

1. In the files, press the project's name at the left above the tree. The menu offers the project, every host set up and {t:workspace.hosts.title}.
2. Press {t:workspace.hosts.title}. Two sections stand in the tree's place: {t:workspace.hosts.title} and {t:workspace.hosts.keys}; with no host it says {t:workspace.hosts.none}
3. If the workspace has no key yet, press {t:workspace.hosts.makeKey} in the {t:workspace.hosts.keys} section. The workspace makes an ed25519 key and the section shows its public half. {t:workspace.hosts.copy} copies it; add it to `~/.ssh/authorized_keys` of the user on the host.
4. Press {t:workspace.hosts.add}. In the dialog enter the {t:workspace.hosts.name} (the name the host goes by in the menu, in the terminal and for agents), the {t:workspace.hosts.address}, the {t:workspace.hosts.port}, the {t:workspace.hosts.user}, a {t:workspace.hosts.path} if you like, and choose the {t:workspace.hosts.key}; with no key the dialog offers {t:workspace.hosts.makeKey}. Press {t:workspace.hosts.add}.
5. Press the host in the list, or {t:workspace.hosts.open} in its row's menu. The tree shows the host's starting folder, and its files are read, downloaded and edited as in a project.
6. Another host, or the project again, is chosen from the same menu above the tree.

{t:workspace.hosts.edit} in the row's menu opens the same dialog with the values filled in. {t:workspace.hosts.remove} asks {t:workspace.hosts.removeTitle} with the note {t:workspace.hosts.removeBody} The files on the host stay untouched. Setting up or removing a host and making the key ask you to confirm who you are, as saving a file does.

### Time worked

1. On the {t:rail.projects} page press {t:workspace.view.hours}, far right in the row with {t:workspace.view.chat} (on a phone in the {t:workspace.view.more} menu).
2. The latest month shows the time by project, {t:workspace.hours.total} and {t:workspace.hours.wall}, and below, under {t:workspace.hours.days}, the same by day, each project in a column of its own.
3. For another month pick it in the {t:workspace.hours.month} field.
4. Writing to Clockify or TaskStreamer and removing transcripts are set up with {t:workspace.hours.settings} ([Writing the time worked](help:agents/hours)).

## How it works

The list is put together from the workspace itself: a project is every folder with Git at the workspace's root, so a new folder appears by itself. A project bears the name of its plan (“Plan DIDA” → DIDA), without one its folder's name with a capital first letter. Projects stand in alphabetical order and keep their place while they are worked on, and beside each stand the chats in use; a chat of an open round stands only in its round, and once the round is closed under its coordinator, indented. To the right of the project's name, on the same line, are the small buttons {t:workspace.newRound}, {t:workspace.newChat}, {t:workspace.terminal.open} and {t:workspace.files.open}. The project's plan opens with {t:workspace.openPlan} from the project's menu (right-click or a long press on its name). A project not being worked on is moved with {t:workspace.others.put} from the project's menu (right-click or a long press on its name): it stands at the bottom under {t:workspace.others}, with the number of such projects, and opens on a click. As soon as a chat or a round starts in it, it returns to the main list by itself and stays there; {t:workspace.others.back} brings it back by hand. The choice is kept with the account, the same on every device. {t:workspace.general} is always at the top. Clicking a project's name shows the rest of its 5 latest chats too, each with the rest of its round, the number beside the name saying how many. The page follows the workspace: when a chat starts or stops working, stops at a question, a round changes or a project's check ends, the page updates by itself, on every device it is open on.

The workspace installs Claude Code itself on its first start, from the Open VSX marketplace of extensions into its home. The chats, the editor's Claude panel and the terminal run the same program with the same sign-in, kept in the workspace, so signing in once in any of them serves all three. It reaches Ponistra with a key the workspace gets by itself when it starts, so Ponistra's MCP server needs no sign-in ([Connecting an outside agent](help:agents/connecting)).

The workspace runs the chats itself: it holds one Claude Code process for each, so neither a new chat or round nor a message, answer, name or closing opens the editor. {t:workspace.openChat} opens only the chat on a phone, without the rest of the editor, and the whole editor with that chat on a computer. Each project has its own browser tab, so a chat of the same project comes into it. The chat is kept in the workspace, so the editor opens the same chat; the workspace then lets its process go, as one chat never runs in two processes. Should it run in two all the same, say in an editor window left open, the workspace stops the older one as soon as it is idle. A message to a chat working in the editor waits until it finishes its step, and the workspace then takes it over. After a restart the workspace carries on with the chats it ran by itself. A chat of an open round and its coordinator, cut short by the restart in the middle of a step, are told to go on from where they stopped; one you stopped yourself waits for you.

The mark {t:workspace.inUse} stands beside a chat that runs, in the workspace or in the editor, and in its place the state when the agent works or waits for you.

The conversation on the page shows your last two questions and everything after them; {t:workspace.earlier} at the top brings the ones before, and your latest question stays pinned at the top while you read below it. Your messages stand on the right, those sent while the agent worked included, the agent's on the left with its formatting (bold, code, lists, tables), what the tool itself told the agent (a background task finished, a message from another session arrived, the conversation was compacted) as a short line in the middle, and consecutive tool calls folded into one line with the number of tools, which opens on a click. While the agent works the conversation is read again every five seconds, otherwise when the agent finishes a step. A message does not go through Ponistra's AI: each is a row in Ponistra's database, and the workspace hands it to that chat's process, as if you had typed it. Images go with the message; beside a message with images the conversation on the page shows how many. An image larger than 1568 pixels on its longer side is scaled down before it is sent. {t:workspace.yes} and {t:workspace.no} answer a permission, and questions with offered answers get an answer each: the chat receives them as if you had chosen them in the editor. A notification on the phone of such a chat bears its first question and has no buttons, but opens the chat.

Every chat has two lines. The first holds its title, state and the time of its last change; state and time each keep a column of their own, the same down the whole list, so a title too long is cut short with an ellipsis before them. The second, smaller, holds {t:workspace.coordinator} for a round's coordinator, the session's name where it differs from the title, and two measures:

- {t:workspace.changes}: how many files this chat changed that hold uncommitted changes, with the lines added and removed. The files counted are those the agent wrote with its editing tools; a change made by a command in the terminal is not seen there. The chats of a round work in the same tree, so the measure says how much uncommitted work stands in that chat's files.
- {t:workspace.context}: how many tokens the agent read last, in thousands. Above 300,000 the number is marked ({t:workspace.contextLarge}), as every next step then costs several times a step in a fresh chat.

At the top of the list, under the heading {t:workspace.host}, stands the state of the server the workspace runs on, each value beside its icon and as a share: {t:workspace.host.cpu} (the load over the last minute against the server's processor threads), {t:workspace.host.memory}, {t:workspace.host.swap} (when the server has it) and the {t:workspace.host.disk} the projects are on. From 90% a value is red. Hold the pointer on a value to see how much of the whole is in use, and on the processor its load and number of threads. The workspace measures the server each time the page reads it: when it opens, at every change the page shows and when you return to it. A click on the values ({t:workspace.host.measure}) measures at once.

Below it, under the heading {t:workspace.limits}, stand the limits of the plan Claude Code in the workspace uses, each as a bar with the share spent: {t:workspace.limits.session} (the five-hour window, when there is one), {t:workspace.limits.week} and the weekly limit of a single model, such as Fable. From 80% the bar is red. Hold the pointer on a bar to see when the limit resets. When credits paid apart from the plan are on, {t:workspace.limits.credits} stands below with the amount, and when a model past its limit runs on credits, {t:workspace.limits.spending} in red instead, with the amount. The workspace measures the limits itself, every five minutes and after a step of a chat it runs, with Claude Code's own program, spending no token and with no sign-in outside it, and the page refreshes itself after each measure. On the right of the heading's line stands {t:workspace.limits.measured} with the time of the last measure. A click on the bars or on the time ({t:workspace.limits.measure}) measures at once and shows the new state within a second or two.

A project's plan is the board titled “Plan <name>” you can read. The plan “Plan OPUS” also belongs to the folders `opus-library` and `opus-player`, as a project's name also matches the beginning of a folder; such a project bears its folder's name.

A project with checks (the folder `.git/ponistra-check`) shows below its name, in red, a check that failed, with {t:workspace.gate.failed} and its time: {t:workspace.gate.browser} (the browser's tests after a push) or {t:workspace.gate.night} (the nightly run of every test, with the number of tests that failed). A failure for a tree that is not the last one pushed carries {t:workspace.gate.older}. A push runs the tests the night failed again; once a check has passed them all, the nightly failure no longer stands in red. While everything passes, nothing stands there.

A round is a set of chats in one project that the coordinator opened at once, each with its own task. The coordinator is given the round's name by itself, the round's goal in a few words it chose while dividing the work (“Kod: limiti i memorija”), in its round and in the list of sessions; a round without a name calls its coordinator {t:workspace.coordinator}. A chat whose task has not been sent yet bears the title from its task's first line. Beside each chat of the round stand its state and the time of its last change:

- {t:workspace.state.new}: the task is written in but not sent yet. Pressing such a chat shows its whole task.
- {t:workspace.state.working}: the agent is working.
- {t:workspace.state.background}: the agent finished its turn, but a command it started in the background, such as a check, still runs.
- {t:workspace.state.waiting}: the agent waits for your answer or permission. Hold the pointer over the mark to see what it waits for.
- {t:workspace.state.idle}: the agent has finished and waits for the next message.
- {t:workspace.state.closed}: the chat runs neither in the workspace nor in the editor.
- {t:workspace.state.cut}: the chat stopped before it answered, as a restart of the workspace, an error or {t:workspace.stop} cut its step short. It is not done until it answers.

{t:workspace.push} sends that word to the coordinator, as if you had typed it, as does consolidating by itself. Until the coordinator has taken it, a line under the round's line names the word sent to it, and {t:workspace.push} is not offered. {t:workspace.push}, {t:workspace.restart}, the terminal and saving a file ask you to confirm who you are first if you have not in the last 8 hours.

{t:workspace.auto} is on for every new round. When every chat of the round is done and the coordinator is not working, the coordinator gets “objedini sam od sebe” and brings the round together without asking; if it was still working then, it gets it as soon as it stops. A chat is done once it has taken at least one step and stopped with its answer; a chat just started, which has not written anything yet, is not, nor is one cut short ({t:workspace.state.cut}), and a coordinator cut short does not get the word either. A word the coordinator had not taken before the round closed is no longer handed over. Should it meet a question, an error or a chat still working, it stops and tells you; the round then waits for you. A push never goes by itself. Once the round closes, its chats and the coordinator stay on the list until you close the coordinator with {t:workspace.close}, even once they no longer run; a message starts any of them again. Only then are the round's chats closed and archived, together with the coordinator. An archived chat you open again later stays on the list.

A command sent to a chat (a message, an answer, a new name, {t:workspace.openChat}, {t:workspace.close}, consolidation, {t:workspace.push}, {t:workspace.archive} or {t:workspace.stop}) stands at the foot of that chat with its state until it is carried out: {t:workspace.progress.sent}, {t:workspace.progress.taken} (the workspace received it) or {t:workspace.progress.failed} with the reason; once {t:workspace.progress.done}, it goes. When archiving fails, the reason also shows below the chat's line, and when a chat does not move to the editor, at the top of the page. The state changes by itself, on every device.

While the round holds unsent chats that were not started, the {t:workspace.start} button stands below the coordinator's row. When the coordinator closes the round, the round leaves the page and its chats stand indented under the coordinator. The workspace stops neither them nor the coordinator by itself, as after bringing the round together it still updates the plan and the memory, pushes, releases and restarts: once all is finished, it writes so into the round's file, and the page then offers it {t:workspace.close} while it is idle, which closes it and its round's chats. A new word you send it from the page ({t:workspace.push}, consolidation or a message) withdraws that offer until it says it is finished again. A coordinator stopped carries on with a message from the page or in the editor. In the editor the round stands as a group in the list of sessions, which every panel puts together when it loads.

A restart makes the workspace again from its Docker Compose definition, with its newest image. It cuts off every chat; those the workspace runs it carries on with by itself, and the others carry on with a message or in the editor. So the button is disabled while a chat works or waits for you, and while a {t:workspace.check} (the nightly or the browser's run) or a {t:workspace.release} runs in the workspace; hold the pointer over the button to see what runs. A run going outside the workspace, such as the nightly one on the server, is not cut off by a restart.

The terminal is the workspace owner's bash shell, the same as in the editor's terminal: it sees the same files, Git, Docker and tools. Each project has a shell of its own in the workspace. It lives until it ends by itself or you close it with {t:workspace.terminal.close}; going to another page, another project's terminal, closing the browser or a lost connection leave it running, and the {t:workspace.terminal.open} icon takes you back into it with everything it wrote in between. Restarting the workspace ends every shell. What the shell writes goes through Ponistra to the browser; the workspace remembers only the last two megabytes of each shell's output, in memory, for coming back to it. The terminal's colours follow the interface's theme. On a computer the terminal is as tall as the page, on a phone three fifths of the screen. At most eight terminals can be open at once.

The workspace itself reads and writes the files; Ponistra only carries them and stores nothing. Every path holds only within the project's folder: a symbolic link leading out stands grey in the tree and is described {t:workspace.files.outside} A link leading nowhere is described {t:workspace.files.broken} Neither opens, nor does an item that is neither a file nor a folder ({t:workspace.files.other}). The `.git` folder at the project's root is not shown. Saving writes the whole file at once, with the same permissions, and only while the disk still holds what the editor loaded: a chat or another session may write to the same tree. If the file changed meanwhile, it says {t:workspace.files.changed} {t:workspace.files.reload} loads what is on the disk now and drops your changes, and {t:workspace.files.overwrite} writes yours over it. While a change is unsaved and the file changes on the disk, the editor keeps your text; otherwise it shows the new content when the page reads it again.

A host is an entry of the workspace's `~/.ssh/config`, and the key a file in `~/.ssh` beside it: the workspace's terminal and agents reach the same host by the same name, and entries of your own in that file stay as they are. The page lists only the entries it set up itself, each with `IdentitiesOnly`, taking the host's key on the first connection; after that the workspace refuses a host whose key changed. The workspace reads and writes the host's files over SFTP, through OpenSSH, so what the other entries say holds too, a jump through another host for one. The starting folder is where the files open, not a fence: the page shows what the user on the host may reach, and an empty starting folder is that user's home. Saving on a host too writes only while the host still holds what the editor loaded. Where it can, it writes a copy beside the file and puts it in the file's place at once, with the same owner, group and permissions; where the user on the host may not write to the folder or give the file its owner, it writes over the file itself, which so keeps its owner. The connection to a host stays open for two minutes after the last request. Nothing on a host is deleted, renamed or uploaded.

The workspace measures the time worked by itself from the chats' transcripts it already reads: every chat's, those in the editor too, each moment a chat wrote down, a message, an answer or a tool. The moments of one project, from all its chats, make a block of work until more than 15 minutes pass between two; a block lasts at least 2 minutes and counts on the day it began, by Croatian time. Projects worked on at once each count in full, so a day's {t:workspace.hours.total} may pass 24 hours; {t:workspace.hours.wall} is the time any project was worked on, without overlap. The project is the folder in the workspace's root the chat began in, also when it began in a subfolder of it; a chat in the root itself counts under {t:workspace.general}. Every minute the workspace reads what is new in the transcripts and tells Ponistra, which keeps the time in its database with a mark of how far each transcript was read; what was once kept stays when a chat's transcript is deleted, and reading the same transcript again counts nothing twice. The page refreshes by itself when new time arrives.

The workspace checks the condition every minute and on every change it reports to the page. Time is Croatian time, so a repeating chat starts at the same hour after the clocks change too. After each start a repeating chat waits for the next time, and every start is a new chat; any other condition starts once. The weekly reset, the five-hour threshold and a red nightly run count only from the moment you set the condition, so a state from before does not meet it. With {t:workspace.when.pause} set, the workspace stops the chats the condition started as soon as the weekly limit reaches that percent, and {t:workspace.paused} shows below the round; once the weekly window is below it again, each stopped chat is told to finish its work. The command of a repeating chat stands at the foot of its latest chat as {t:workspace.progress.waiting}.

A change in the workspace also sends its owner a push notification: a chat waits for a decision, a round is ready, a round was consolidated, the browser's or the nightly run failed, and the round's coordinator finished a step with a message or waits for your input. It also tells you when the plan's weekly limit or a model's own limit passes 80%, and when a model past its limit starts spending credits, each once per week of the limit. The notification of a chat or coordinator that waits carries the buttons {t:workspace.yes} and {t:workspace.no}, which answer as in the chat on the page, without opening Ponistra; if the answer does not go through, the Projects page opens. Which notifications arrive is set in [Notifications](help:account/notifications).

## Limits

The page exists only for the owner of the code workspace.

- {t:error.not_the_owner} Only the user it was assigned to sees the workspace.
- {t:error.workspace_not_linked} The installation has no workspace token. The installation's administrator links the workspace on the server, as the installation guide describes.
- {t:error.workspace_unreachable} The workspace is not running, or its token differs from the installation's. It also shows for a few seconds during a restart.
- {t:error.no_round} The round was closed and removed meanwhile. The page updates by itself.
- {t:error.round_closed} The coordinator has already closed the round, so it is no longer started or brought together.
- {t:error.round_started} The round has already started, so it takes no condition any more.
- {t:error.no_condition} The round or the chat has started meanwhile, or its condition was called off.
- {t:error.invalid_when} The time has passed or carries no time zone, the percent is not between 1 and 100, or the round waited on does not exist.
- {t:error.no_chat} The chat no longer exists in the workspace.
- {t:error.no_project} The folder is not a project of the workspace.
- {t:error.unknown_folder} The project is no longer in the workspace. Close the files and open them from the project in the list.
- {t:error.outside} The path leads out of the project's folder through a symbolic link; open files outside the project in the workspace's terminal or editor.
- {t:error.invalid_path} The path is not valid.
- {t:error.not_found} The file or folder was deleted or renamed meanwhile.
- {t:error.not_permitted} The user the workspace runs as may not read or write that file or folder.
- {t:error.too_large} The text grew past 1 MB, so it is not saved from the editor.
- {t:error.unknown_host} The host was removed or renamed meanwhile. Choose it again from the menu above the tree.
- {t:error.ssh_key_refused} The public key chosen for the host is not in the `authorized_keys` of the user on the host, or the user is wrong.
- {t:error.ssh_key_unreadable} The key's file in the workspace's `~/.ssh` is damaged or its permissions are too wide.
- {t:error.host_unreachable} The host does not answer at the address and port, or the connection broke during a request.
- {t:error.host_unknown} The name in the address resolves to no IP address.
- {t:error.host_key_changed} The host presents another key than at the first connection; if that is expected (a host installed anew), remove the old key from the workspace's `~/.ssh/known_hosts` in the terminal.
- {t:error.host_key_unknown} An entry of your own for the host in the SSH settings asks for a known host key, and the workspace has none.
- {t:error.ssh_config_invalid} SSH does not accept the workspace's `~/.ssh/config`; correct the file in the terminal or the editor.
- {t:error.sftp_missing} The host has no SFTP server turned on.
- {t:error.sftp_garbled} The shell of the user on the host prints text even when not interactive, so SFTP cannot work.
- {t:error.host_failed} The host refused the action for no reason SFTP names; the message is in the workspace's log.
- {t:error.host_closed} The host was removed or changed while the request waited.
- {t:error.host_exists} The workspace's `~/.ssh/config` already holds an entry of that name.
- {t:error.key_exists} The workspace's key already exists; no new one is made over it.
- {t:error.invalid_host} {t:error.invalid_host_address} {t:error.invalid_host_port} {t:error.invalid_host_user} {t:error.invalid_host_key} A host's entry takes only what the SSH settings can write.
- {t:error.asked} The coordinator was already sent a word it has not taken yet.
- {t:error.not_waiting} The chat got its answer meanwhile.
- {t:error.chat_working} The chat started working or asking between the press and the handover, so it was not opened in the editor.
- {t:error.chat_busy} A message to a chat working in the editor waits for it to finish its step; if it does not within an hour, the message fails.
- {t:error.no_agent} The Claude Code extension, whose program runs the chats, is not installed in the workspace. The workspace installs it when it starts and tries again at every start while it is missing; until then install Claude Code from the editor's Extensions view.
- {t:error.not_ended} The chat's process did not stop.
- {t:error.too_many_images} A message takes at most four images; the rest are not added.
- {t:error.image_type} The image is not PNG, JPEG, GIF or WebP.
- {t:error.image_too_large} The image is larger than 3.75 MB even scaled down. A GIF is not scaled down.
- {t:error.image_unread} The browser could not scale the image down.
- {t:error.invalid_images} A message takes only images you uploaded yourself, of an allowed kind and size.
- {t:error.known_command} The workspace has already received the same command.
- {t:error.invalid_command} The workspace does not know that command.
- {t:error.invalid_session} The command carries no valid chat id.
- {t:error.invalid_round} The command carries no valid round id.
- {t:error.workspace_busy} Something started running between opening the page and confirming.
- {t:error.restart_running} The previous restart is still going.
- {t:error.no_docker} The workspace has no access to Docker, so the restart button is not shown; an installation gets it only when the agent was given Docker.
- {t:error.not_in_docker} The workspace was not started as a Docker container.
- {t:error.not_from_compose} The workspace was not started through Docker Compose, so there is no definition to make it again from.
- {t:error.compose_moved} The folder holding the workspace's definition was moved after it started. Start it once from the new folder (`docker compose up -d --force-recreate`), and the button works by itself again.
- {t:error.restart_failed} Docker Compose could not make the workspace again; what it said stands in the workspace's log, and the workspace goes on running as before.

A chat without a title, such as one with no answer yet, is not on the list. The limits are those of one plan, the one Claude Code in the workspace is signed in with, so chats outside it spend them too; the page shows the last measure, at most five minutes old. Claude Code gives this as an experimental figure, so a shape the workspace does not know shows as {t:workspace.limits.unread} rather than as a zero. When the workspace cannot read the server's state, {t:workspace.host.unread} stands in place of the values.

## Related

- [Writing the time worked](help:agents/hours)
- [Token spend](help:agents/spend)
- [Agent's memory](help:agents/memory)
- [Connecting an outside agent](help:agents/connecting)
- [Spoken commands](help:start/voice)
- [Notifications](help:account/notifications)
- [The application frame](help:start/overview)
