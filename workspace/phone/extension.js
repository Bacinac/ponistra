const fs = require('fs');
const os = require('os');
const path = require('path');
const vscode = require('vscode');

const run = (command, ...args) => vscode.commands.executeCommand(command, ...args);

const isChat = (tab) =>
  tab.input instanceof vscode.TabInputWebview && tab.input.viewType.endsWith('claudeVSCodePanel');

const chats = () => vscode.window.tabGroups.all.flatMap((group) => group.tabs).filter(isChat);

// Not editor.open, which turns the owner's preferred location into the panel on every device.
const openChat = (session) => run('claude-vscode.primaryEditor.open', session);

const ARCHIVED = path.join(os.homedir(), '.claude', 'ponistra-archived.json');

const readJson = (file) => {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return undefined;
  }
};

// A window that loads brings back the tabs its folder last had open in any window, and Claude Code
// starts the chat of each, so a chat archived since would come back to life. Claude Code replaces a
// revived tab with a new one a little later, which the grace still covers; projects.mjs keeps a chat
// archived unless it stays open longer than that.
const STARTED = Date.now();
const REVIVING = 30 * 1000;

const unrevived = (tabs, spared) => {
  const labels = new Set(
    (readJson(ARCHIVED) ?? [])
      .filter((each) => each.id !== spared && each.label && each.at < STARTED)
      .map((each) => each.label),
  );
  const revived = tabs.filter((tab) => isChat(tab) && labels.has(tab.label));
  if (!revived.length) return;
  vscode.window.tabGroups
    .close(revived)
    .then(undefined, (error) =>
      vscode.window.showErrorMessage(`An archived chat did not close: ${error.message}`),
    );
};

const followTabs = (spared) =>
  vscode.window.tabGroups.onDidChangeTabs(({ opened }) => {
    if (Date.now() - STARTED < REVIVING) unrevived(opened, spared);
  });

exports.activate = async (context) => {
  const config = vscode.workspace.getConfiguration('ponistra');
  const phone = config.get('phone');
  const asked = config.get('chat');
  unrevived(chats(), asked);
  context.subscriptions.push(followTabs(asked));
  if (!phone && !asked) return;
  try {
    if (phone) {
      await run('workbench.action.closeSidebar');
      await run('workbench.action.closeAuxiliaryBar');
      await run('workbench.action.closePanel');
    }
    if (asked) await openChat(asked);
    else if (!chats().length) await openChat();
  } catch (error) {
    vscode.window.showErrorMessage(`The chat did not open: ${error.message}`);
  }
};
