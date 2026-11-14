# Meetings relay

An administrator sets the external TURN service through which a meeting's picture and sound reach participants outside the organisation's network when the installation has no ports open inward.

## How to use it

### Cloudflare

1. Open {t:admin.title} and choose {t:relay.title}.
2. Under {t:relay.provider} choose Cloudflare.
3. Enter the {t:relay.keyId} and the {t:relay.token} of a TURN key from Cloudflare's dashboard.
4. Press {t:ai.save}.

### Another TURN service

1. Under {t:relay.provider} choose {t:relay.turn}.
2. Under {t:relay.addresses} enter the service's addresses, each on a line of its own, for example `turn:turn.example.com:3478` and `turns:turn.example.com:443?transport=tcp`.
3. Enter the {t:relay.username} and the {t:relay.password}, then press {t:ai.save}.

### Turning it off

1. Under {t:relay.provider} choose {t:relay.none}.
2. Press {t:ai.save}.

## How it works

Without an external relay the browser gets what the installation's meeting server offers: a direct connection and, where the installation has one, its own relay. Participants on the organisation's network, or connected to it, have meetings without any setting.

With an external relay, every joining of a meeting, a member's or a guest's, gets the relay's addresses and credentials in place of the meeting server's relay. The browser reaches the relay outward, and the meeting server answers the relay outward too, so no port towards the installation has to be open.

With Cloudflare the installation asks for credentials valid for one day with the key and the token, and gives them to each joining. It asks for new ones once less than 12 hours are left of the old, so credentials never expire in the middle of a meeting. Before saving, the installation tries the key with Cloudflare; a key it refuses is not saved.

The token or password is kept sealed with the installation's secret and is not shown again, except its last 4 characters beside {t:relay.kept}. Leave the token or password field empty to keep the saved value; when you change the provider, you have to enter it again. Turning the relay off also deletes the saved value. Each change is written to the [journal](help:admin/journal), with {t:ai.changed} on the page.

## Limits

- Only an administrator of the installation sees and changes the setting.
- While an external relay is set but cannot be had, joining a meeting is refused rather than the participant joining without the relay:
  - {t:error.relay_refused} The key was revoked or the token lacks the permission; enter a valid one.
  - {t:error.relay_unreachable} The installation cannot reach the provider; check the installation's connection outward.
  - {t:error.relay_lost} The installation's secret has changed; enter the token or password again.
- An incomplete setting is not saved; instead one of these shows:
  - {t:error.relay_name_needed}
  - {t:error.relay_address_needed}
  - {t:error.invalid_relay_address}
  - {t:error.relay_secret_needed}
- The meeting server must be allowed to send UDP traffic outward.

## Related

- [Guests](help:meetings/guests)
- [Meetings](help:meetings/overview)
- [Installation health](help:admin/health)
