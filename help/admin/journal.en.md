# Journal

The journal records what happened to the installation as a whole: sign-ins and failed sign-ins, changes to users, groups and keys, the administrator's settings and the problems Ponistra found by itself.

## How to use it

1. Open {t:admin.title} and choose {t:journal.title}.
2. Entries stand newest first. Each shows {t:log.when}, {t:log.who}, {t:log.what} and the {t:journal.address} the request came from.
3. Under {t:journal.group}, choose {t:journal.group.all}, {t:journal.group.sign_ins}, {t:journal.group.accounts}, {t:journal.group.settings} or {t:journal.group.health}.
4. Under {t:journal.person}, choose a user to see only what they did or what was done to them, or {t:journal.everyone}.
5. For entries older than those shown, press {t:journal.more} at the bottom of the list.

While no entry matches the choice, it says {t:journal.none}

## How it works

### What is written

Under {t:journal.group.sign_ins}: {t:journal.kind.signed_in} (with a password, a passkey, {t:journal.way.oidc} or {t:journal.way.saml}, and holding the pointer over the row shows the browser), {t:journal.kind.sign_in_failed} with the email address typed, {t:journal.kind.locked_out}, {t:journal.kind.signed_out}, {t:journal.kind.sessions_ended} (when a user or an administrator signs devices out) and {t:journal.kind.application_signed_in}, when someone signs in to another application through Ponistra.

Under {t:journal.group.accounts}: {t:journal.kind.installed}, {t:journal.kind.user_added}, {t:journal.kind.user_changed} with what changed (name, email address, administrator role, being active, password, groups), {t:journal.kind.user_erased} with the heir of the documents, {t:journal.kind.group_added}, {t:journal.kind.group_renamed}, {t:journal.kind.group_removed}, {t:journal.kind.password_changed}, {t:journal.kind.passkey_added}, {t:journal.kind.passkey_removed}, {t:journal.kind.app_password_added} and {t:journal.kind.app_password_removed}.

Under {t:journal.group.settings}: {t:journal.kind.policy_changed}, {t:journal.kind.application_added}, {t:journal.kind.application_changed}, {t:journal.kind.application_removed}, {t:journal.kind.application_secret}, {t:journal.kind.provider_added}, {t:journal.kind.provider_changed}, {t:journal.kind.provider_removed}, {t:journal.kind.provider_secret} and {t:journal.kind.setting_changed}, with the setting's name: {t:journal.setting.ai}, {t:journal.setting.ai_monthly}, {t:journal.setting.speech}, {t:journal.setting.mail_client}, {t:journal.setting.mail_opened}, {t:journal.setting.push}, {t:journal.setting.resource}, {t:journal.setting.hours}, {t:journal.setting.workdays}, {t:journal.setting.closures}, {t:journal.setting.offsite}, {t:journal.setting.offsite_kit}, {t:journal.setting.retention} and {t:journal.setting.legal_hold}.

Under {t:journal.group.health}: {t:journal.kind.problem} and {t:journal.kind.resolved}, which Ponistra writes itself, so it is named as the user.

### Keeping and privacy

The journal is kept for a year; the next sign-in deletes older entries. Passwords, keys and secrets are never written. When a user is erased, their sign-ins, sign-outs, keys and the failed sign-ins under their address go with them, and what they did to others as an administrator stays without their name. A person's data export carries their journal entries too.

The journal refreshes itself as soon as something new happens. Who opened, downloaded and shared documents and folders shows in each document's access log, and the vault keeps a log of its own.

## Limits

- Only an administrator opens the journal.
- Changes made by commands on the server, not through Ponistra, are not written.
- The address is the one the proxy in front of Ponistra hands it; behind a proxy that does not, the proxy's own address is written.

## Related

- [System health](help:admin/health)
- [Users](help:admin/users)
- [Sign-in and sharing rules](help:admin/policy)
