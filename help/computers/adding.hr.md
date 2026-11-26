# Dodavanje računala

Administrator za novo računalo izrađuje datoteku `install.conf` s jednokratnim kodom, pa se računalo s Ponistra OS-om instalira sa sticka bez pitanja i samo upiše u Ponistru.

## Kako se koristi

1. Otvorite {t:rail.computers} ili {t:admin.title}, {t:computers.title}.
2. Pritisnite {t:computers.add} i potvrdite da ste to vi.
3. Odaberite {t:computers.install.role}: {t:computers.install.role.workstation} ili {t:computers.install.role.server}.
4. Upišite {t:computers.install.hostname}. Prazno polje znači {t:computers.install.hostname.auto}.
5. Odaberite {t:computers.install.language} ({t:computers.install.language.hr} ili {t:computers.install.language.en}) i {t:computers.install.keyboard}: {t:computers.install.keyboard.language}, {t:computers.install.keyboard.hr} ili {t:computers.install.keyboard.us}.
6. Pod {t:computers.install.network} odaberite {t:computers.install.network.dhcp} ili {t:computers.install.network.static}. Za stalnu adresu upišite {t:computers.install.address} u obliku `192.0.2.20/24 gateway 192.0.2.1 dns 1.1.1.1`.
7. Radnoj stanici koja se spaja bežično upišite {t:computers.install.wifi} i {t:computers.install.wifiPassword}. Poslužitelju upišite {t:computers.install.sshKey}, po jedan ključ ili adresu popisa ključeva u retku, ili `none`.
8. Upišite {t:computers.install.password} i ponovite je u polju {t:computers.install.passwordAgain}.
9. Ako disk smije biti obrisan, uključite {t:computers.install.erase}.
10. Pritisnite {t:computers.install.make}. Pojavljuje se {t:computers.code} s rokom ({t:computers.code.expires}).
11. Pritisnite {t:computers.install.download}. {t:computers.install.onStick}
12. Pod {t:computers.sticks} preuzmite {t:computers.stick.network} ili {t:computers.stick.full} trenutačnog izdanja i zapišite ga na stick prije nego što na nj kopirate datoteku.

## Kako radi

Kod vrijedi 7 dana i samo za jedno računalo, a prikazuje se samo jednom; Ponistra pamti samo njegov sažetak, a u popisu {t:computers.codes} pokazuje njegov završetak. Datoteka nosi javnu adresu ove Ponistre, kod i lozinku računa admin kao argon2id sažetak, nikad samu lozinku. Lozinka Wi-Fi mreže zapisuje se u datoteku kakva jest, pa stick nakon instalacije čuvajte ili obrišite.

Računalo se pri prvom pokretanju upiše u Ponistru tim kodom i preda joj ključ za oporavak diska. Vi postajete njegov prvi upravitelj, a računalo se pojavljuje u {t:rail.computers}. Račun admin služi za vlastitu stranicu računala na njegovoj adresi u lokalnoj mreži.

Odgovori se provjeravaju kao što ih provjerava instalacija, pa stick ne staje zbog krive vrijednosti. Ono što ostane prazno, kao uloga ili naziv, instalacija pita u obrascu na mobitelu ili računalu u istoj mreži. {t:computers.install.network.dhcp} je zadana mreža, a disk se bez {t:computers.install.erase} briše samo ako je prazan ili na njemu već je Ponistra OS.

{t:computers.stick.network} je manji i sustav preuzima tijekom instalacije; {t:computers.stick.full} ga nosi sa sobom. Popis izdanja Ponistra čita s poslužitelja izdanja Ponistra OS-a.

## Ograničenja

- Dodaje samo administrator, a kod traži [potvrdu da ste to vi](help:account/confirm).
- {t:computers.install.passwordDiffers}
- {t:computers.error.public_url_not_https}
- {t:computers.error.name_taken} Odaberite drugi naziv ili ostavite polje prazno.
- {t:computers.error.invalid_name}
- {t:computers.error.invalid_network} Adresa ne smije biti adresa same mreže, a pristupnik mora biti u njoj.
- {t:computers.error.invalid_wifi}
- {t:computers.error.invalid_wifi_password}
- {t:computers.error.wifi_server}
- {t:computers.error.invalid_ssh_key} Ključ se piše u jednom retku, kao u datoteci `.pub`; `none` ne ide uz druge ključeve.
- {t:computers.error.invalid_password}
- {t:computers.error.release_unreachable} Datoteka i kod vrijede i dalje; stick preuzmite kasnije.

## Povezano

- [Računala](help:computers/computers)
- [Potvrda da ste to vi](help:account/confirm)
