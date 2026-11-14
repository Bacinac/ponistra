# Projects

The desk of your code workspace: projects with their rounds and chats, a conversation with the agent right on the page, and the activity of everything you asked of the workspace.

## How to use it

### A new chat

1. On the bar of modules press {t:rail.projects}.
2. Find the project. {t:workspace.general} is the workspace as a whole, for chats that belong to no single project.
3. Press the {t:workspace.newChat} icon right of the project's name (its name shows when the mouse rests on it).
4. The form opens in the chat's place (on a phone in place of the list), the cursor already in its field. In the field {t:workspace.newChatText} type the first message, or press {t:speech.dictate} and say it. Images are added as in a message on the page.
5. Press {t:workspace.startChat} or Enter, as in a message on the page. The chat starts in the workspace and shows in the form's place; the editor does not open.

### Back to a chat

1. On the {t:rail.projects} page find the chat under its project. Closed chats stand behind the project's name: press the name.
2. Press the title of a closed chat. It shows beside the list, as a chat in use does.
3. Send it a message and the workspace carries on with it. To carry on with it in the editor, press {t:workspace.openChat}.

### Talking to the agent on the page

1. On the {t:rail.projects} page press a chat. On a phone {t:workspace.view.chat} then opens (the buttons at the top switch between {t:workspace.view.overview}, {t:workspace.view.chat}, [{t:workspace.view.memory}](help:agents/memory) and {t:workspace.view.hours}); on a computer the list stands in the left column, like the folders beside documents, and the chat to its right, until the {t:workspace.view.memory} button, far right in the row with {t:workspace.view.chat}, replaces it with the agent's memory. Each scrolls on its own, and the list is widened or narrowed by dragging the thin line between the list and the chat. Until you pick one, the coordinator of the latest round is shown.
2. In the field {t:workspace.say} type a message, or press {t:speech.dictate} and say it.
3. For an image, paste it into the field (Ctrl+V), drag it onto the field or press {t:workspace.addImage}. It shows small below the field; {t:workspace.removeImage} takes it off before sending. A right click in the field pastes the clipboard's text where the caret stands, or its image when it holds no text. If the browser does not let the clipboard be read, below the field it says: {t:error.clipboard_refused}
4. Press {t:workspace.send} or Enter; Shift+Enter starts a new line, and on a phone Enter starts a new line, so the button sends. For frequent words press {t:workspace.quick.catchup}, {t:workspace.quick.continue} or {t:workspace.quick.handoff}; each is sent at once. A message you send stands at the foot of the conversation at once. Until the agent reads it, it is framed and below it says {t:workspace.unread}; the agent reads it when it finishes the step it is on, and it then becomes part of the conversation.
5. For the text of the agent's answer press {t:workspace.copy} below it; a code block has a {t:workspace.copy} of its own in its top right corner, which copies the code alone. The button shows {t:workspace.copied} for a moment, or {t:workspace.copyFailed} if the browser does not allow writing to the clipboard.
6. The {t:workspace.model} the chat runs on stands beside {t:workspace.send}. Press it and choose another; it holds from the next answer. If the chat runs in the editor, the change waits until it is idle, and the workspace then takes it over. The models offered are those Claude Code in the workspace offers, and the model stays when the workspace restarts.
7. While the agent works or waits for you, {t:workspace.stop} stands beside {t:workspace.send}. Press it and the agent breaks off what it does, as Esc does in the editor; a permission it waited for is refused, and the chat stays open for your next message. A chat working in the editor is stopped there, so the button is disabled.
8. For the whole chat in the editor press {t:workspace.openChat}. While the agent works or waits for you, the button is disabled.

### Answering a chat that waits

1. On the {t:rail.projects} page, while a chat waits, {t:workspace.waitingForYou} stands at the top of the list (on a phone in {t:workspace.view.overview}, the number beside that button saying how many chats wait).
2. There stands every chat waiting for your answer or permission, with what it asks.
3. Press {t:workspace.yes} or {t:workspace.no}. A question offering answers can also be answered in your own words: pick the chat, type them into the field {t:workspace.say} and send them.

The same {t:workspace.yes} and {t:workspace.no} also stand in the conversation when a waiting chat is selected.

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
2. The form opens in the chat's place. In the field {t:workspace.newRoundText} type what the round should do, or press {t:speech.dictate} below the field and say it. The field may stay empty: the coordinator then takes the next steps from the project's plan.
3. Press {t:workspace.openRound} or Enter. The workspace starts a coordinator with the message “nastavi: …” and shows it in the form's place; the editor does not open.
4. The coordinator divides the work into chats. The round appears on the page, and beside each chat not yet sent stands its task: press the chat to read it.

### A round of chats

1. On the {t:rail.projects} page find the round under its project. The round begins with the row of {t:workspace.coordinator}, the chat that opened the round and bears its name, and below the coordinator, indented, stand the round's chats.
2. If the chats have not started yet, press {t:workspace.start}. The workspace starts each chat of the round with the task written for it.
3. Press a chat of the round to read it in the conversation on the page. {t:workspace.openChat} opens it in the editor.
4. When every chat of the round is done, the coordinator brings the round's work together by itself as soon as it is idle, while {t:workspace.auto} is on in its menu. With it off, write “objedini” to the coordinator when you want it.

5. Once the work is brought together, the check found it green and no push has carried it yet, {t:workspace.push} stands below the coordinator's row instead; when the coordinator has already closed the round, the button stands below its row in the project's list of chats. Press it. The coordinator then pushes the work; a release to production still needs your explicit word in the chat.

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

Going to {t:rail.projects} again brings that same window forward rather than opening another. {t:meeting.nextScreen} in the window's header moves it to the next screen and fills it, when the computer has more than one; this needs permission to manage windows in the site's settings. A narrow window has the buttons for the chat and the memory as on a phone, a wide one the list and the chat side by side, the list as wide as you drag its separator, as in Ponistra's tab. A notification of the workspace opens in that window while it is open. The window takes a new version of Ponistra once you put it out of sight, unless a terminal or an unsent message is open in it. If the browser does not allow a window of its own, the page opens in Ponistra's tab and says so; pop-ups are allowed in the browser's settings for the site, and the {t:workspace.beside} icon in the header then tries again. On a phone the page opens in the tab. The page can have a theme other than the rest of Ponistra's, in the tab and in its own window: {t:frame.theme.projects} in the account menu ([Theme and language](help:start/appearance)).

### Terminal

1. On the {t:rail.projects} page press the {t:workspace.terminal.open} icon to the right of the project's name.
2. If you have not confirmed who you are in the last 8 hours, confirm it.
3. The terminal opens in the chat's place, in the project's folder. Type commands as in any terminal; Ctrl+C stops a command. A right click pastes the clipboard's text, and when something in the terminal is selected, copies the selection.
4. The {t:workspace.view.terminal} button at the top brings the terminal back while you look at a chat or the memory; a command in it keeps running meanwhile.
5. {t:workspace.terminal.close} at the right above the terminal closes it and ends the shell with everything started in it.

When the shell ends (the `exit` command) or the connection to it is lost, the terminal closes by itself; the {t:workspace.terminal.open} icon opens a new shell. If the terminal cannot be opened, below it says: {t:workspace.terminal.unopened} {t:workspace.terminal.reopen} tries again.

### Time worked

1. On the {t:rail.projects} page press {t:workspace.view.hours}, far right in the row with {t:workspace.view.chat} (on a phone with {t:workspace.view.overview}).
2. The latest month shows the time by project, {t:workspace.hours.total} and {t:workspace.hours.wall}, and below, under {t:workspace.hours.days}, the same by day, each project in a column of its own.
3. For another month pick it in the {t:workspace.hours.month} field.
4. Writing to Clockify or TaskStreamer and removing transcripts are set up in [Writing the time worked](help:agents/hours).

## How it works

The list is put together from the workspace itself: a project is every folder with Git at the workspace's root, so a new folder appears by itself. A project bears the name of its plan (“Plan DIDA” → DIDA), without one its folder's name with a capital first letter. Projects stand in alphabetical order and keep their place while they are worked on, and beside each stand the chats in use; a chat of an open round stands only in its round, and once the round is closed under its coordinator, indented. To the right of the project's name, on the same line, are the small buttons {t:workspace.newRound}, {t:workspace.newChat} and {t:workspace.terminal.open}. The project's plan opens with {t:workspace.openPlan} from the project's menu (right-click or a long press on its name). Below the name, indented like the chats and reaching no further than those buttons, stands the latest push; the other checks (the browser and the night run) are folded behind the arrow with a number at the end of that line ({t:workspace.gate}) and open with a click, each on a line of its own; when a check failed, the arrow is red, as is that check. A project not being worked on is moved with {t:workspace.others.put} from the project's menu (right-click or a long press on its name): it stands at the bottom under {t:workspace.others}, with the number of such projects, and opens on a click. As soon as a chat or a round starts in it, it returns to the main list by itself and stays there; {t:workspace.others.back} brings it back by hand. The choice is kept with the account, the same on every device. {t:workspace.general} is always at the top. Clicking a project's name shows the rest of its 5 latest chats too, each with the rest of its round, the number beside the name saying how many. The page follows the workspace: when a chat starts or stops working, stops at a question, a round changes or a project's check ends, the page updates by itself, on every device it is open on.

The workspace runs the chats itself: it holds one Claude Code process for each, so neither a new chat or round nor a message, answer, name or closing opens the editor. {t:workspace.openChat} opens only the chat on a phone, without the rest of the editor, and the whole editor with that chat on a computer. Each project has its own browser tab, so a chat of the same project comes into it. The chat is kept in the workspace, so the editor opens the same chat; the workspace then lets its process go, as one chat never runs in two processes. Should it run in two all the same, say in an editor window left open, the workspace stops the older one as soon as it is idle. A message to a chat working in the editor waits until it finishes its step, and the workspace then takes it over. After a restart the workspace carries on with the chats it ran by itself.

The mark {t:workspace.inUse} stands beside a chat that runs, in the workspace or in the editor, and in its place the state when the agent works or waits for you.

The conversation on the page shows your last two questions and everything after them; {t:workspace.earlier} at the top brings the ones before, and your latest question stays pinned at the top while you read below it. Your messages stand on the right, those sent while the agent worked included, the agent's on the left with its formatting (bold, code, lists, tables), what the tool itself told the agent (a background task finished, a message from another session arrived, the conversation was compacted) as a short line in the middle, and consecutive tool calls folded into one line with the number of tools, which opens on a click. While the agent works the conversation is read again every five seconds, otherwise when the agent finishes a step. A message does not go through Ponistra's AI: each is a row in Ponistra's database, and the workspace hands it to that chat's process, as if you had typed it. Images go with the message; beside a message with images the conversation on the page shows how many. An image larger than 1568 pixels on its longer side is scaled down before it is sent. {t:workspace.yes} and {t:workspace.no} answer the permission or question the chat asked.

Every chat has two lines. The first holds its title, state and the time of its last change; state and time each keep a column of their own, the same down the whole list, so a title too long is cut short with an ellipsis before them. The second, smaller, holds {t:workspace.coordinator} for a round's coordinator, the session's name where it differs from the title, and two measures:

- {t:workspace.changes}: how many files this chat changed that hold uncommitted changes, with the lines added and removed. The files counted are those the agent wrote with its editing tools; a change made by a command in the terminal is not seen there. The chats of a round work in the same tree, so the measure says how much uncommitted work stands in that chat's files.
- {t:workspace.context}: how many tokens the agent read last, in thousands. Above 300,000 the number is marked ({t:workspace.contextLarge}), as every next step then costs several times a step in a fresh chat.

At the top of the list, under the heading {t:workspace.host}, stands the state of the server the workspace runs on, each value beside its icon and as a share: {t:workspace.host.cpu} (the load over the last minute against the server's processor threads), {t:workspace.host.memory}, {t:workspace.host.swap} (when the server has it) and the {t:workspace.host.disk} the projects are on. From 90% a value is red. Hold the pointer on a value to see how much of the whole is in use, and on the processor its load and number of threads. The workspace measures the server each time the page reads it: when it opens, at every change the page shows and when you return to it. A click on the values ({t:workspace.host.measure}) measures at once.

Below it, under the heading {t:workspace.limits}, stand the limits of the plan Claude Code in the workspace uses, each as a bar with the share spent: {t:workspace.limits.session} (the five-hour window, when there is one), {t:workspace.limits.week} and the weekly limit of a single model, such as Fable. From 80% the bar is red. Hold the pointer on a bar to see when the limit resets. When credits paid apart from the plan are on, {t:workspace.limits.credits} stands below with the amount, and when a model past its limit runs on credits, {t:workspace.limits.spending} in red instead, with the amount. The workspace measures the limits itself, every five minutes and after a step of a chat it runs, with Claude Code's own program, spending no token and with no sign-in outside it, and the page refreshes itself after each measure. On the right of the heading's line stands {t:workspace.limits.measured} with the time of the last measure. A click on the bars or on the time ({t:workspace.limits.measure}) measures at once and shows the new state within a second or two.

A project's plan is the board titled “Plan <name>” you can read. The plan “Plan OPUS” also belongs to the folders `opus-library` and `opus-player`, as a project's name also matches the beginning of a folder; such a project bears its folder's name.

A project with checks (the folder `.git/ponistra-check`) shows the state of its gate once you open {t:workspace.gate} below its name:

- {t:workspace.gate.checked}: when the check before a push last passed.
- {t:workspace.gate.browser}: the browser's tests that run after a push, {t:workspace.gate.passed} or {t:workspace.gate.failed}, with the time.
- {t:workspace.gate.night}: the nightly run of every test, and with a failure the number of tests that failed.

While a run is going, {t:workspace.gate.running} stands instead of its outcome. An outcome for a tree that is not the last one pushed carries {t:workspace.gate.older}. A failure is marked.

A round is a set of chats in one project that the coordinator opened at once, each with its own task. The coordinator is given the round's name by itself, the round's goal in a few words it chose while dividing the work (“Kod: limiti i memorija”), in its round and in the list of sessions; a round without a name calls its coordinator {t:workspace.coordinator}. A chat whose task has not been sent yet bears the title from its task's first line. Beside each chat of the round stand its state and the time of its last change:

- {t:workspace.state.new}: the task is written in but not sent yet. Pressing such a chat shows its whole task.
- {t:workspace.state.working}: the agent is working.
- {t:workspace.state.background}: the agent finished its turn, but a command it started in the background, such as a check, still runs.
- {t:workspace.state.waiting}: the agent waits for your answer or permission. Hold the pointer over the mark to see what it waits for.
- {t:workspace.state.idle}: the agent has finished and waits for the next message.
- {t:workspace.state.closed}: the chat runs neither in the workspace nor in the editor.

{t:workspace.push} sends that word to the coordinator, as if you had typed it, as does consolidating by itself. Until the coordinator has taken it, a line under the round's line names the word sent to it, and {t:workspace.push} is not offered. {t:workspace.push}, {t:workspace.restart} and the terminal ask you to confirm who you are first if you have not in the last 8 hours.

{t:workspace.auto} is on for every new round. When every chat of the round is done and the coordinator is not working, the coordinator gets “objedini sam od sebe” and brings the round together without asking; if it was still working then, it gets it as soon as it stops. A chat is done once it has taken at least one step and stopped; a chat just started, which has not written anything yet, is not. A word the coordinator had not taken before the round closed is no longer handed over. Should it meet a question, an error or a chat still working, it stops and tells you; the round then waits for you. A push never goes by itself. Once the round closes, its chats are closed and archived; the coordinator stays on the list until it has done its part. An archived chat you open again later stays on the list.

A command sent to a chat (a message, an answer, a new name, {t:workspace.openChat}, {t:workspace.close}, consolidation, {t:workspace.push}, {t:workspace.archive} or {t:workspace.stop}) stands at the foot of that chat with its state until it is carried out: {t:workspace.progress.sent}, {t:workspace.progress.taken} (the workspace received it) or {t:workspace.progress.failed} with the reason; once {t:workspace.progress.done}, it goes. When archiving fails, the reason also shows below the chat's line, and when a chat does not move to the editor, at the top of the page. The state changes by itself, on every device.

While the round holds unsent chats that were not started, the {t:workspace.start} button stands below the coordinator's row. When the coordinator closes the round, the round leaves the page and the workspace stops its chats. It stops the coordinator only once it is idle, as after bringing the round together it still pushes, releases and restarts, and not at all while it leads another round still open. A coordinator stopped carries on with a message from the page or in the editor. In the editor the round stands as a group in the list of sessions, which every panel puts together when it loads.

A restart makes the workspace again from its Docker Compose definition, with its newest image. It cuts off every chat; those the workspace runs it carries on with by itself, and the others carry on with a message or in the editor. So the button is disabled while a chat works or waits for you, and while a {t:workspace.check} (the nightly or the browser's run) or a {t:workspace.release} runs in the workspace; hold the pointer over the button to see what runs. A run going outside the workspace, such as the nightly one on the server, is not cut off by a restart.

The terminal is the workspace owner's bash shell, the same as in the editor's terminal: it sees the same files, Git, Docker and tools. Each terminal on the page is a shell of its own in the workspace and lives while the page is open; closing the terminal, going to another page, a new terminal for another project or a lost connection ends it, and with it whatever was started in it. For work that has to outlive closing it, use the editor's terminal or `nohup`. What the shell writes goes through Ponistra to the browser and is stored nowhere. The terminal's colours follow the interface's theme. On a computer the terminal is as tall as the page, on a phone three fifths of the screen. At most eight terminals can be open at once.

The workspace measures the time worked by itself from the chats' transcripts it already reads: every chat's, those in the editor too, each moment a chat wrote down, a message, an answer or a tool. The moments of one project, from all its chats, make a block of work until more than 15 minutes pass between two; a block lasts at least 2 minutes and counts on the day it began, by Croatian time. Projects worked on at once each count in full, so a day's {t:workspace.hours.total} may pass 24 hours; {t:workspace.hours.wall} is the time any project was worked on, without overlap. The project is the folder in the workspace's root the chat began in, also when it began in a subfolder of it; a chat in the root itself counts under {t:workspace.general}. Every minute the workspace reads what is new in the transcripts and tells Ponistra, which keeps the time in its database with a mark of how far each transcript was read; what was once kept stays when a chat's transcript is deleted, and reading the same transcript again counts nothing twice. The page refreshes by itself when new time arrives.

A change in the workspace also sends its owner a push notification: a chat waits for a decision, a round is ready, a round was consolidated, the browser's or the nightly run failed, and the round's coordinator finished a step with a message or waits for your input. It also tells you when the plan's weekly limit or a model's own limit passes 80%, and when a model past its limit starts spending credits, each once per week of the limit. The notification of a chat or coordinator that waits carries the buttons {t:workspace.yes} and {t:workspace.no}, which answer as in the chat on the page, without opening Ponistra; if the answer does not go through, the Projects page opens. Which notifications arrive is set in [Notifications](help:account/notifications).

## Limits

The page exists only for the owner of the code workspace.

- {t:error.not_the_owner} Only the user it was assigned to sees the workspace.
- {t:error.workspace_not_linked} The installation has no workspace token. The installation's administrator enters it.
- {t:error.workspace_unreachable} The workspace is not running, or its token differs from the installation's. It also shows for a few seconds during a restart.
- {t:error.no_round} The round was closed and removed meanwhile. The page updates by itself.
- {t:error.round_closed} The coordinator has already closed the round, so it is no longer started or brought together.
- {t:error.no_chat} The chat no longer exists in the workspace.
- {t:error.no_project} The folder is not a project of the workspace.
- {t:error.asked} The coordinator was already sent a word it has not taken yet.
- {t:error.not_waiting} The chat got its answer meanwhile.
- {t:error.chat_working} The chat started working or asking between the press and the handover, so it was not opened in the editor.
- {t:error.chat_busy} A message to a chat working in the editor waits for it to finish its step; if it does not within an hour, the message fails.
- {t:error.no_agent} The Claude Code extension, whose program runs the chats, is not installed in the workspace.
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

A chat without a title, such as one with no answer yet, is not on the list. The limits are those of one plan, the one Claude Code in the workspace is signed in with, so chats outside it spend them too; the page shows the last measure, at most five minutes old. Claude Code gives this as an experimental figure, so a shape the workspace does not know shows as {t:workspace.limits.unread} rather than as a zero. When the workspace cannot read the server's state, {t:workspace.host.unread} stands in place of the values.

## Related

- [Writing the time worked](help:agents/hours)
- [Agent's memory](help:agents/memory)
- [Connecting an outside agent](help:agents/connecting)
- [Spoken commands](help:start/voice)
- [Notifications](help:account/notifications)
- [The application frame](help:start/overview)
