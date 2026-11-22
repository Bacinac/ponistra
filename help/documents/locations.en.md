# Network locations

A network location is a folder on a server, together with the account Ponistra signs in to it with; it is added in the settings, and its files open in Documents.

## How to use it

### A shared folder (SMB)

1. In the settings open {t:locations.settings} and press {t:locations.add}.
2. Under {t:explorer.kind} leave {t:locations.kind.smb}.
3. Enter {t:tree.name} and {t:locations.address} as `\\server\share`, with a subfolder if you wish.
4. Enter {t:locations.username} (for a domain `DOMAIN\user`) and {t:locations.auth.password}. Enter {t:locations.port} only if it is not 445.
5. If the server stands in another network, choose under {t:locations.tunnel} the tunnel that reaches it; {t:locations.tunnelNone} means straight.
6. Press {t:tree.save} or {t:tree.cancel}.

### An SSH server (SFTP)

1. Press {t:locations.add} and under {t:explorer.kind} choose {t:locations.kind.sftp}.
2. Enter {t:tree.name}, {t:locations.host} and, if it is not 22, {t:locations.port}.
3. Under {t:locations.path} enter the folder on the server the location starts from; empty means the account's home folder.
4. Enter {t:locations.username} and under {t:locations.auth} choose {t:locations.auth.password} or {t:locations.auth.key}.
5. If the server is reached only through another one, enter that one under {t:locations.jump} as `user@server:port`.
6. If the server stands in another network, choose under {t:locations.tunnel} the tunnel that reaches it.
7. Press {t:tree.save}.
8. With a key, the public key appears below the location. Press {t:locations.copyKey} and add it to `~/.ssh/authorized_keys` of the account on the server and, if the location goes through another server, of the account on that one too.

### Changing, sharing and removing

1. In the location's row open the actions menu.
2. {t:locations.edit} opens the same fields; the password changes only if you enter a new one.
3. {t:access.share} opens the access list: add a person, a group or all users and choose {t:access.role.read}, {t:access.role.edit} or {t:access.role.own}.
4. {t:locations.remove} removes the location after a confirmation.

A location's name in the list opens its [files](help:documents/network).

## How it works

When a location with a password is saved, Ponistra signs in to the server at once, so a location with a wrong address or sign-in is not saved. A location with a key is saved without signing in, as the key works only once you add it to the server.

The password and the private key are kept encrypted with the installation's secret key and are never shown, not even to the owner. Ponistra makes the key, a separate one for each location, and its private half never leaves the installation.

At the first sign-in to an SSH server Ponistra remembers the key the server presented. If it presents another one later, the connection is refused until the owner saves the location again; changing the server, the port, the server gone through or the tunnel remembers the key anew.

A location with a tunnel reaches its server only through it, never straight, and the server's name is resolved in the network behind the tunnel. With a server to go through, the tunnel carries the connection to that server, which leads on to the location. Tunnels are set up by an administrator; {t:locations.tunnel} offers only those switched on and appears only once there is at least one. In the list of locations the tunnel's name follows the address.

Everyone the location is shared with works on the server with the same account, the location's. The role in Ponistra decides only whether they may read or also change, and only the owner sees and changes the location's settings. Whoever a location is shared with sees the owner's name in this list in place of the menu.

Removing a location takes it from everyone, and the files on the server stay untouched.

## Limits

- Who may add a location is decided by an administrator. Where you are not allowed, there is no {t:locations.add} button, and an attempt reports {t:error.locations_off} Locations shared with you still open.
- Adding, changing, sharing and removing may ask you to [confirm that it is you](help:account/confirm).
- The server has to be reachable from the server Ponistra runs on, not from your device. Otherwise it says {t:error.location_unreachable} or {t:error.location_host_unknown}
- {t:error.location_login} means a wrong user name or password, or a key not yet added to the server.
- {t:error.location_sftp_missing} means the SSH server does not allow that account to transfer files.
- {t:error.location_not_found} means the folder entered is not on the server.
- {t:error.location_tunnel_down} means the location's tunnel is not connected right now or an administrator switched it off; the location works again once the tunnel connects.
- {t:error.invalid_tunnel} means the chosen tunnel is no longer switched on.
- {t:error.invalid_jump} and {t:error.invalid_location_name} describe the field to correct.

## Related

- [Files on the network](help:documents/network)
- [Sharing](help:documents/sharing)
- [Confirming that it is you](help:account/confirm)
