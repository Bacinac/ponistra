# Blocked senders and images by domain

You can send the mail of a sender or a whole domain to junk or to a chosen folder, and decide for each domain whether images show.

## How to use it

### Blocking

1. Open a message from the sender. Bulk mail has {t:mail.block} on the bar, other messages in the menu of further actions.
2. In the {t:mail.blockTitle} dialog choose the address or {t:mail.wholeDomain}.
3. Press {t:mail.blockConfirm}.

### Always moving

1. Choose {t:mail.always} in the open message's menu of further actions.
2. In the {t:mail.alwaysTitle} dialog choose the address or {t:mail.wholeDomain}, and {t:mail.ruleFolder}.
3. Confirm.

### Reviewing rules

1. Open Settings, then {t:mail.senders}.
2. Under {t:mail.rules} is the list of rules ({t:mail.rulesNone} when there are none). Press {t:mail.unrule} beside a rule to remove it.
3. Under {t:mail.decidedTitle} are domains marked {t:mail.imagesShown} or {t:mail.imagesQuiet} ({t:mail.decidedNone} when there are none). Removing a domain holds its images again until you allow them.

## How it works

A rule applies at once to the mail you already have and to each message arriving later, before it enters a folder, so a blocked message causes no notification. When several rules concern a sender, the narrowest decides: an address comes before a domain, and a domain includes its subdomains.

Rules take no messages out of sent mail, drafts, the trash and junk. Rules apply only in Ponistra and to all your accounts.

Moving a message out of junk with {t:mail.notJunk} removes the block that sent it there.

At the bottom of the mail settings, under {t:mail.keys}, stand the keys you encrypt with: your own from the vault and recipients' keys Ponistra remembered from signed messages or you loaded yourself ({t:mail.keysBring})

## Limits

- Rules look only at the sender, not at the subject or content.
- Removing a rule does not bring back messages already moved.
- For an address without a domain with a dot, {t:mail.wholeDomain} is not offered.

## Related

- [Reading a message](help:mail/reading)
- [Working with several messages](help:mail/selecting)
- [Encrypted and signed mail](help:mail/encrypted)
