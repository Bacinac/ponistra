# Connecting an outside agent

An outside agent, such as Claude, ChatGPT or another MCP client, signs in through your account and works in Ponistra with your rights.

## How to use it

### Connecting

1. Open {t:settings.title} and choose {t:agents.title}.
2. Press {t:agents.copy} beside the {t:agents.url}.
3. In the agent add that address as an MCP server.
4. The agent opens the page {t:agents.consent.title} in the browser. If you are not signed in, sign in first.
5. Check who asks for access, your account under {t:agents.consent.as} and under {t:agents.consent.returns} the address the sign-in returns to. Below {t:agents.consent.can} the page lists what the agent may do.
6. Press {t:agents.consent.allow} or {t:agents.consent.deny}.

### Revoking

1. Under {t:agents.title} find the agent in the list.
2. Press {t:agents.revoke} and confirm in the dialog {t:agents.revokeTitle}

## How it works

The agent acts as you: it sees the documents, mail, calendar, tasks and contacts you see and nothing more. What it writes into a document comes as a proposal with its name beside yours, a reply it drafts waits for you to send it, and the actions it starts show like your own. The agent deletes nothing and sends no mail.

The list under {t:agents.title} has the columns {t:agents.client}, {t:agents.connected} and {t:agents.used}. Once you revoke an agent, it can no longer read or write, and what it wrote stays.

When an agent starts an action Claude carries out, no separate permission of the document is asked: the consent was given when the agent was connected.

## Limits

- For {t:agents.consent.allow} Ponistra may ask you to confirm that it is you.
- An agent does not accept or reject proposals; you do.
- When no agent is connected, it says: {t:agents.none}

## Related

- [What an agent can do](help:agents/tools)
- [Proposals](help:ai/proposals)
- [Confirming it is you](help:account/confirm)
