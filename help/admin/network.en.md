# Network

The page shows the installation's public address, whether meetings reach it from outside the local network, and keeps the token that keeps the DNS records on that address.

## How to use it

### Ports for meetings

1. Open {t:admin.title} and choose {t:network.title}.
2. Under {t:network.meetings} read the {t:network.address} and the state of the ports in the row below it: {t:network.reached} or {t:network.unreached}.
3. If it says {t:network.unreached}, forward both ports of that row on the router to the installation's server, UDP 7882 and TCP 7881 by default, then open the page again.

### The token for the DNS records

The part {t:network.names} shows only where the installation has names pointing straight at its public address: the relay's name, and the domain where the installation fetches its certificate itself.

1. At Cloudflare, make an API token with Zone: Read and DNS: Edit for the zone of those names.
2. Enter it in {t:network.token} and press {t:ai.save}.
3. To replace it, enter the new token over the saved one and press {t:ai.save} again.
4. To remove it, press {t:network.forget}.

## How it works

The {t:network.address} is the address the internet sees the server by; the installation learns it from a public STUN server each time the page opens, and where that does not answer it says {t:network.unknown}. It then connects to the meetings' TCP port at that address, as a browser outside would. If it connects, it says {t:network.reached}. Meetings' sound and picture go through the installation's server, so without those two ports nobody outside the local network receives them, not through an outside relay either. Inside the local network meetings work without them.

{t:network.relay} shows the name of the relay for networks that let out only HTTPS, or {t:network.noRelay}. The owner of the server sets it with the command `ponistra relay <name>`, with TCP 443 and UDP 3478 forwarded; `ponistra relay none` removes it.

The token is tried at Cloudflare before it is saved and kept sealed with the installation's secret key; afterwards only its last four characters are shown beside {t:network.kept}, and the field offers {t:network.replace}. Every two minutes the installation checks its public address and, when it changes, points the names' records at it, making a record that does not exist. When that fails, the field shows {t:network.refused} with Cloudflare's answer. Saving and removing the token are written to the [journal](help:admin/journal) as {t:journal.setting.network_dns}.

[System health](help:admin/health) checks both and tells the administrators when meetings from outside or the DNS records stop working.

[VPN tunnels](help:admin/tunnels) into another network are set up on the same page, under {t:network.tunnels}, and below them [Docker hosts](help:admin/docker) under {t:docker.hosts}.

## Limits

- The ports are checked through the installation's own public address. A router that does not loop traffic back to its own address shows {t:network.unreached} though it may work from outside; then check with a call from a mobile network.
- Only the TCP port is checked; the meetings' server does not answer an unknown sender on the UDP port, so forward both.
- The token works only where Cloudflare keeps the zone of those names.
- {t:error.dns_token_refused} means Cloudflare does not know the token or it was revoked: make a new one.

## Related

- [VPN tunnels](help:admin/tunnels)
- [Docker hosts](help:admin/docker)
- [System health](help:admin/health)
- [Administration](help:admin/administration)
- [Guests in a meeting](help:meetings/guests)
