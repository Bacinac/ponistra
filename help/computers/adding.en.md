# Adding a computer

An administrator makes an `install.conf` file with a one-time code for a new computer, so the Ponistra OS computer installs from a stick without questions and enrolls in Ponistra by itself.

## How to use it

1. Open {t:rail.computers} or {t:admin.title}, {t:computers.title}.
2. Press {t:computers.add} and confirm it is you.
3. Choose the {t:computers.install.role}: {t:computers.install.role.workstation} or {t:computers.install.role.server}.
4. Type the {t:computers.install.hostname}. An empty field means {t:computers.install.hostname.auto}.
5. Choose the {t:computers.install.language} ({t:computers.install.language.hr} or {t:computers.install.language.en}) and the {t:computers.install.keyboard}: {t:computers.install.keyboard.language}, {t:computers.install.keyboard.hr} or {t:computers.install.keyboard.us}.
6. Under {t:computers.install.network}, choose {t:computers.install.network.dhcp} or {t:computers.install.network.static}. For a static address, type the {t:computers.install.address} as `192.0.2.20/24 gateway 192.0.2.1 dns 1.1.1.1`.
7. For a workstation that connects wirelessly, type the {t:computers.install.wifi} and the {t:computers.install.wifiPassword}. For a server, type the {t:computers.install.sshKey}, one key or address of a key list per line, or `none`.
8. Type the {t:computers.install.password} and repeat it in {t:computers.install.passwordAgain}.
9. If the disk may be erased, turn on {t:computers.install.erase}.
10. Press {t:computers.install.make}. The {t:computers.code} appears with its deadline ({t:computers.code.expires}).
11. Press {t:computers.install.download}. {t:computers.install.onStick}
12. Under {t:computers.sticks}, download the current release's {t:computers.stick.network} or {t:computers.stick.full} and write it to the stick before copying the file onto it.

## How it works

The code is valid for 7 days and for one computer only, and it is shown only once; Ponistra keeps only its digest and shows its end in {t:computers.codes}. The file carries this Ponistra's public address, the code, and the admin account's password as an argon2id hash, never the password itself. The Wi-Fi password is written into the file as it is, so keep or wipe the stick after the installation.

At its first start the computer enrolls in Ponistra with the code and hands over its disk recovery key. You become its first manager, and the computer appears in {t:rail.computers}. The admin account is for the computer's own page at its address in the local network.

The answers are checked as the installation checks them, so the stick does not stop on a wrong value. What is left empty, such as the role or the name, the installation asks in a form on a phone or computer in the same network. {t:computers.install.network.dhcp} is the default network, and without {t:computers.install.erase} the disk is erased only if it is empty or already holds Ponistra OS.

The {t:computers.stick.network} is smaller and downloads the system during the installation; the {t:computers.stick.full} carries it. Ponistra reads the release list from Ponistra OS's release server.

## Limits

- Only an administrator adds a computer, and the code asks you to [confirm it is you](help:account/confirm).
- {t:computers.install.passwordDiffers}
- {t:computers.error.public_url_not_https}
- {t:computers.error.name_taken} Choose another name or leave the field empty.
- {t:computers.error.invalid_name}
- {t:computers.error.invalid_network} The address may not be the network's own address, and the gateway must be within the network.
- {t:computers.error.invalid_wifi}
- {t:computers.error.invalid_wifi_password}
- {t:computers.error.wifi_server}
- {t:computers.error.invalid_ssh_key} A key is written on one line, as in a `.pub` file; `none` does not go with other keys.
- {t:computers.error.invalid_password}
- {t:computers.error.release_unreachable} The file and the code stay valid; download the stick later.

## Related

- [Computers](help:computers/computers)
- [Confirming it is you](help:account/confirm)
