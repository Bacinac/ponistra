# VPN tunnels

A tunnel opens a standing connection for the installation into another network, through WireGuard or SoftEther, and shows whether that connection is up.

## How to use it

### New tunnel

1. Open {t:admin.title} and choose {t:network.title}.
2. Under {t:network.tunnels} press {t:network.tunnelNew}.
3. Enter a {t:network.tunnelName} you will know the tunnel by.
4. Under {t:network.tunnelKind} choose WireGuard or SoftEther.
5. For WireGuard paste into {t:network.configuration} the configuration the other network's administrator gave you, or press {t:network.configurationFile} and choose the `.conf` file.
6. For SoftEther enter the {t:network.server}, {t:network.port} (443 by default), {t:network.hub}, {t:network.username} and {t:network.password}.
7. Leave {t:network.tunnelEnabled} ticked and press {t:tree.create}.

### Changing, switching off and removing

1. In the tunnel's row open {t:tree.actions}.
2. {t:network.tunnelEdit} opens the same form without the choice of kind. The secret's field stays empty, marked {t:network.configurationReplace} or {t:network.passwordReplace}: an empty field keeps the saved secret, a new value replaces it. Press {t:tree.save}.
3. {t:network.tunnelOff} closes the connection and keeps the tunnel saved; {t:network.tunnelOn} opens it again.
4. {t:network.tunnelDelete}, once confirmed, closes the connection and deletes the tunnel together with its saved secret.

## How it works

The tunnels are held by a service of the installation of its own, `tunnel`. The server hands them to it on every save and hands them again by itself when the service starts anew, so tunnels work after a restart of the server or an update without anything from you. Only connections Ponistra opens go through a tunnel; the server the installation runs on and its other networks are not routed through it.

The WireGuard configuration and the SoftEther password are kept sealed with the installation's secret key and are never shown again. The tunnel's row shows its kind, the other side's address (the Endpoint for WireGuard, server and port for SoftEther) and, while the tunnel is up, the address the installation has in the other network.

The state at the right of the row changes by itself as soon as the service tells it; hold the pointer over it for the time since when it holds:

- {t:network.state.connecting}: the tunnel has just been handed over or the connection is being made again.
- {t:network.state.up}: the connection works.
- {t:network.state.failed}: the connection could not be opened; the reason stands under the name.
- {t:network.state.off}: the tunnel is switched off.
- {t:network.state.unreached}: the server gets no answer from the service `tunnel`; the tunnels are handed over again as soon as it answers.

WireGuard runs inside the service and asks the installation's host for no device and no special rights. It takes the address, keys, DNS servers and peers from the configuration; an address without a mask gets /32. Where a peer sets no PersistentKeepalive, one is sent every 25 seconds so the connection stays open through NAT. The tunnel is {t:network.state.up} while the last key exchange with a peer is less than 3 minutes old. A host name in the Endpoint is resolved again at most once a minute, so the tunnel follows a change of the other side's address.

SoftEther connects to a virtual hub of a SoftEther VPN server with a username and password, gets its address in the other network from that network's DHCP and resolves names through the DNS servers the DHCP names. Each tunnel has a routing table of its own, so two tunnels into networks with the same addresses do not collide. When the connection drops, it connects again every 15 seconds.

Adding, changing and removing a tunnel are written to the [journal](help:admin/journal) as {t:journal.setting.network_tunnel} with the tunnel's name.

## Limits

- Only an administrator sees and changes tunnels, and saving, changing and removing one ask for [confirmation](help:account/confirm).
- A tunnel's kind does not change once saved; for the other kind add a new tunnel.
- SoftEther signs in with a password only, not a certificate, and does not verify the server's certificate.
- SoftEther needs the device `/dev/net/tun` from the installation's host; WireGuard does not.
- Settings only `wg-quick` acts on (Table, PostUp, SaveConfig and the like) and DNS search domains are not read from a WireGuard configuration.

The messages under a tunnel's name:

- {t:network.tunnelError.no_answer}: the other side's server did not answer. Check the address and port, and that the other side's firewall lets traffic in from the installation's public address.
- {t:network.tunnelError.refused}: the username, password or key were not accepted. Enter them again or ask for new ones.
- {t:network.tunnelError.no_hub}: the SoftEther server has no hub of that name; check the {t:network.hub}.
- {t:network.tunnelError.no_device}: the installation's host does not give the device `/dev/net/tun`. The host's owner adds it as the installation guide says.
- {t:network.tunnelError.dhcp}: the connection is open but the other network's DHCP gave no address. DHCP has to run on the SoftEther side (SecureNAT or the network's own).
- {t:network.tunnelError.resolve}: the name in the Endpoint does not resolve; check it.
- {t:network.tunnelError.sealed} Open {t:network.tunnelEdit} and enter the configuration or password again.
- {t:network.tunnelError.failed}: any other reason; the text after the message is the service's answer.
- {t:error.invalid_wireguard} The configuration lacks one [Interface] with PrivateKey and Address or at least one [Peer] with PublicKey and Endpoint, or a key is not a WireGuard key.
- {t:error.tunnel_taken} Choose another name.

## Related

- [Network](help:admin/network)
- [Journal](help:admin/journal)
