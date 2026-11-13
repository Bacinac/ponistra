// What the Claude panel needs from the page that hosts its webview: node webview.mjs <pre/index.html>
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';

const PANEL = `if (new URLSearchParams(location.search).get('extensionId') === 'Anthropic.claude-code') {
	const selecting = () => !contentWindow.getSelection().isCollapsed;
	let pressed = false;
	let held = false;
	// The panel moves the cursor to its prompt whenever its window gains focus. When the press that
	// gave it focus is a drag, the selection goes with it and Ctrl+C silently leaves the old clipboard,
	// so the focus waits for the release, and a plain click still lands in the prompt.
	contentWindow.addEventListener('pointerdown', () => { pressed = true; }, true);
	contentWindow.addEventListener('focus', e => {
		if (pressed) { held = true; }
		if (pressed || selecting()) { e.stopImmediatePropagation(); }
	}, true);
	const release = e => {
		const plainClick = held && e.button === 0 && !selecting();
		pressed = false;
		held = false;
		if (plainClick) { contentWindow.dispatchEvent(new contentWindow.Event('focus')); }
	};
	contentWindow.addEventListener('pointerup', release, true);
	contentWindow.addEventListener('pointercancel', release, true);
	// Inline code is no link, so the panel offers no Copy Link, and Copy without a selection copies nothing.
	contentWindow.addEventListener('contextmenu', e => {
		const code = e.target.closest('code');
		if (code && !selecting()) { contentWindow.getSelection().selectAllChildren(code); }
	}, true);
}
`;
// A round of chats (skills nastavi and objedini) lives in ~/.claude/ponistra-rounds/<round>.json on the
// server, read through projects.mjs beside code-server, which runs its chats. Session groups live in
// each browser, so every panel draws the rounds of its folder into groups of its own when it loads.
const ROUNDS = `if (new URLSearchParams(location.search).get('extensionId') === 'Anthropic.claude-code') {
	contentWindow.addEventListener('load', () => {
		const contentDocument = contentWindow.document;
		const GROUP = 'ponistra-round-';
		const served = location.pathname.slice(0, location.pathname.indexOf('/stable-')) + '/ponistra';
		const base = served + '/rounds';
		let folder = null;
		try { folder = new URLSearchParams(window.top.location.search).get('folder'); } catch {}
		if (!folder || !contentDocument.getElementById('root')) { return; }
		const query = '?folder=' + encodeURIComponent(folder);
		const asked = new Map();
		contentWindow.addEventListener('message', e => {
			const message = e.data?.type === 'from-extension' && e.data.message;
			const answer = message?.type === 'response' && asked.get(message.requestId);
			if (!answer) { return; }
			asked.delete(message.requestId);
			answer(message.response);
		}, true);
		const ask = request => new Promise(resolve => {
			const requestId = 'ponistra-' + crypto.randomUUID();
			asked.set(requestId, resolve);
			hostMessaging.postMessage('onmessage', { message: { type: 'request', requestId, request } });
		});
		const label = round => {
			const at = /-(\\d{4})(\\d{2})(\\d{2})-(\\d{2})(\\d{2})$/.exec(round);
			return at ? 'Krug ' + Number(at[3]) + '.' + Number(at[2]) + '. ' + at[4] + ':' + at[5] : 'Krug ' + round;
		};
		// The extension drops every group when one fails its check and keeps a session in the first
		// group that names it, so a group keeps its exact shape and never takes a session of the owner's.
		const draw = async rounds => {
			const { groups } = await ask({ type: 'get_session_groups' });
			const byId = new Map(rounds.map(r => [GROUP + r.round, r]));
			const foreign = new Set(groups.filter(g => !g.id.startsWith(GROUP)).flatMap(g => g.sessionIds));
			const next = [];
			const archive = [];
			for (const group of groups) {
				const round = group.id.startsWith(GROUP) ? byId.get(group.id) : undefined;
				if (group.id.startsWith(GROUP) && (!round || round.closed)) {
					if (round) { archive.push(...round.chats.map(c => c.sessionId).filter(Boolean)); }
					continue;
				}
				next.push(group);
			}
			for (const round of rounds) {
				if (round.closed) { continue; }
				const known = [round.coordinator, ...round.chats.map(c => c.sessionId)].filter(id => id && !foreign.has(id));
				const at = next.findIndex(g => g.id === GROUP + round.round);
				if (at < 0) {
					next.unshift({ id: GROUP + round.round, name: label(round.round), collapsed: false, sessionIds: known });
				} else {
					const group = next[at];
					next[at] = { ...group, sessionIds: [...new Set([...group.sessionIds, ...known])] };
				}
			}
			if (JSON.stringify(next) !== JSON.stringify(groups)) { await ask({ type: 'update_session_groups', groups: next }); }
			for (const sessionId of archive) { await ask({ type: 'archive_session', sessionId }); }
		};
		// One panel of the folder in this browser follows the rounds and draws their groups; when its
		// page goes, the next one waiting takes the lock.
		let drawing = Promise.resolve();
		navigator.locks.request('ponistra-rounds:' + folder, () => new Promise(() => {
			const events = new EventSource(base + '/events' + query);
			events.onmessage = e => {
				const { rounds } = JSON.parse(e.data);
				drawing = drawing.then(() => draw(rounds)).catch(console.error);
			};
		}));
	}, { once: true });
}
`;
const ANCHOR = "contentWindow.addEventListener('click', handleInnerClick);";
// A page may not paste through execCommand, and in Edge its copy from the menu leaves the clipboard
// as it was, so the panel's menu goes through the async clipboard its frame is allowed.
const MENU = `if (new URLSearchParams(location.search).get('extensionId') === 'Anthropic.claude-code') {
	const chosen = contentDocument.getSelection();
	if (data === 'paste') {
		if (contentDocument.activeElement === contentDocument.body) {
			chosen.removeAllRanges();
			target.contentWindow.dispatchEvent(new target.contentWindow.Event('focus'));
		}
		target.contentWindow.focus();
		navigator.clipboard.readText().then(text => contentDocument.execCommand('insertText', false, text), console.error);
		return;
	}
	if (data === 'copy' && !chosen.isCollapsed) {
		target.contentWindow.focus();
		navigator.clipboard.writeText(chosen.toString()).catch(console.error);
		return;
	}
}
`;
const MENU_ANCHOR = 'contentDocument.execCommand(data);';
const OPEN = '<script async type="module">';
const POLICY = "default-src 'none';";

const sha256 = (text) => `'sha256-${createHash('sha256').update(text).digest('base64')}'`;

const [path] = process.argv.slice(2);
const html = readFileSync(path, 'utf8');
const start = html.indexOf(OPEN) + OPEN.length;
const end = html.indexOf('</script>', start);
const script = html.slice(start, end);
if (!html.includes(sha256(script))) throw new Error(`${path}: its policy does not name the hash of its script`);
if (script.split(ANCHOR).length !== 2) throw new Error(`${path}: expected one frame hookup`);
if (script.split(MENU_ANCHOR).length !== 2) throw new Error(`${path}: expected one menu command`);
if (html.split(POLICY).length !== 2) throw new Error(`${path}: expected one policy`);

const patched = script.replace(ANCHOR, () => `${PANEL}${ROUNDS}${ANCHOR}`).replace(MENU_ANCHOR, () => `${MENU}${MENU_ANCHOR}`);
// The page reaches projects.mjs for the rounds, from the address it came from.
const head = html.slice(0, start).replace(POLICY, () => `${POLICY} connect-src 'self';`);
writeFileSync(path, head.replace(sha256(script), sha256(patched)) + patched + html.slice(end));
