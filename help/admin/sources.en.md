# Outside sign-in and directories

An administrator connects Ponistra to the organisation's sign-in provider (OpenID Connect or SAML) and to its directory (LDAP, Active Directory or SCIM), so people sign in with the organisation's account and accounts and groups come from the directory.

## How to use it

### Sign-in provider (OpenID Connect or SAML)

1. On the {t:users.title} page, in the {t:sources.title} section, press {t:sources.new}.
2. Type {t:sources.name}, the name people see on the button of the sign-in page.
3. Under {t:sources.kind} choose {t:sources.kind.oidc} or {t:sources.kind.saml}. For OpenID Connect also type {t:sources.field.issuer}.
4. Press {t:sources.next}. The dialog now shows the addresses you enter at the provider, each with a copy button: for OpenID Connect {t:sources.here.redirect_uri}, for SAML {t:sources.here.entity_id}, {t:sources.here.acs_url} and {t:sources.here.metadata_url}.
5. At the provider, register Ponistra with those addresses.
6. For OpenID Connect type the {t:sources.field.client_id} and {t:sources.field.secret} the provider gave. For SAML type {t:sources.field.metadata_url} or paste {t:sources.field.metadata}.
7. If needed, type {t:sources.domains} and turn on {t:sources.creates} and {t:sources.groups}.
8. Under {t:sources.advanced}, if needed, change {t:sources.field.scopes} (by default `openid email profile`) and {t:sources.field.groups_claim} (by default `groups`) for OpenID Connect, and {t:sources.field.email_attribute} and {t:sources.field.groups_attribute} for SAML, when the provider sends them under names Ponistra does not recognise by itself.
9. Leave {t:sources.enabled} on and press {t:tree.save}.

### LDAP or Active Directory directory

1. Press {t:sources.new} and under {t:sources.kind} choose {t:sources.kind.ldap}.
2. Type {t:sources.field.url} (`ldaps://…`, or `ldap://…` with {t:sources.field.starttls} on), {t:sources.field.bind_dn}, {t:sources.field.password} and {t:sources.field.base_dn}.
3. Turn on {t:sources.field.sign_in} if people sign in with their directory password.
4. Under {t:sources.field.every} set how often the directory is read.
5. Under {t:sources.advanced}, if needed, type {t:sources.field.user_filter}, {t:sources.field.group_base_dn}, {t:sources.field.group_filter}, {t:sources.field.email_attribute} and {t:sources.field.ca}.
6. Press {t:tree.create}. Ponistra connects to the directory at once and says so if it fails.

### SCIM directory

1. Press {t:sources.new}, under {t:sources.kind} choose {t:sources.kind.scim} and press {t:tree.create}.
2. Copy the {t:sources.here.scim_url} and the {t:sources.token} and enter them at the provider (for example in the application's user provisioning). The token is shown only then.
3. You issue a new token from the source's actions menu, {t:sources.renew}, and confirm in the {t:sources.renewTitle} dialog

### The list of sources

1. Each source in the list shows its name, its kind, {t:sources.off} when it is turned off, {t:sources.synced} with the time it was last read and its number of people ({t:sources.people}). Below is the last error, if there is one.
2. In the actions menu: {t:sources.edit}, {t:sources.sync} (an LDAP directory and SAML with a metadata URL), {t:sources.renew} (SCIM) and {t:sources.delete}, which asks for confirmation in the {t:sources.deleteTitle} dialog

## How it works

A person signs in at the provider with the button bearing the source's name on the sign-in page. Ponistra recognises them the first time by their verified email address, and from then on by the identifier the provider gave them, so a change of address at the provider does not change the account. When {t:sources.domains} are given, only addresses in those domains are accepted. With {t:sources.creates} a person without an account gets a new one; otherwise an administrator makes the account first. A provider that creates accounts must have domains, or anyone with an account at a public provider would get one.

For OpenID Connect, Ponistra reads the provider's description from the issuer's address when you save the settings and then once a day. SAML metadata at an address is read once a day and at once on {t:sources.sync}; pasted metadata holds until you replace it. A sign-in must end in the browser where it started and within 10 minutes, and each answer of the provider counts once. The client secret and the directory password are kept encrypted and are not shown again; the field then shows {t:sources.keepSecret}, and the metadata {t:sources.keepMetadata}.

An LDAP directory is read every 60 minutes, or as often as you set between 5 and 1440, and at once after saving. A SCIM directory sends its changes itself as they happen. A person who comes from a directory has the email address, name, password and active state the directory has: in the {t:users.edit} dialog those fields are disabled, and the list of users shows the source's name beside the name. A person turned off in the directory (in Active Directory, a disabled account) is deactivated and signed out of every device, and so is a person the directory no longer lists. Their account and documents stay until an administrator erases them.

With {t:sources.field.sign_in}, the directory's people sign in on the sign-in page with their address and their directory password, which Ponistra checks with the directory at every sign-in and never stores. Their own password in Ponistra stops working, except for administrators, who can so still get in while the directory is unreachable.

With {t:sources.groups}, groups come from the source: an existing group of the same name is taken over, and a group whose name is taken gets the source's name in brackets. Such a group cannot be renamed or deleted, and the source decides who is in it. A group the source no longer has is removed, unless something would be left without an owner; it then stays as a group of the installation.

When you remove a source, the people and groups it brought stay as the installation's own accounts and groups. Adding, changing and removing a source and a new token are written to the [journal](help:admin/journal), and so are sign-ins at a provider.

## Limits

- The passkey policy does not apply to signing in at a provider; any further check (a second factor, for example) is then the provider's.
- Encrypted SAML assertions (EncryptedAssertion) are not accepted. The provider must sign the response or the assertion.
- An LDAP directory must be reached encrypted: {t:error.unencrypted_directory}
- Nested groups of an LDAP directory are not unfolded: a member is only whom the group names directly.
- The last active administrator is not deactivated, even when the directory turns them off.
- A source that creates accounts cannot be saved without domains: {t:error.domains_required}
- A source turned on without its secret or metadata is not saved: {t:error.secret_required} {t:error.metadata_required}
- When the provider or the directory is unreachable or refuses the connection, saving and the list below the source say one of these, so check the address, the bind DN and the password: {t:error.provider_unreachable} {t:error.directory_unreachable} {t:error.directory_refused}
- If the issuer in the provider's description differs from the one typed, it says {t:error.provider_mismatch}
- Adding, changing and removing a source and a new token may ask you to confirm it is you.

## Related

- [Users](help:admin/users)
- [Groups](help:admin/groups)
- [Signing in and the sign-in method](help:account/sign-in)
- [Journal](help:admin/journal)
