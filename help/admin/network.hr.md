# Mreža

Stranica pokazuje javnu adresu instalacije, dolaze li sastanci do nje izvan lokalne mreže i čuva token kojim DNS zapisi prate tu adresu.

## Kako se koristi

### Portovi za sastanke

1. Otvorite {t:admin.title} i odaberite {t:network.title}.
2. Pod {t:network.meetings} pročitajte {t:network.address} i stanje portova u retku ispod nje: {t:network.reached} ili {t:network.unreached}.
3. Ako piše {t:network.unreached}, na usmjerivaču proslijedite na poslužitelj instalacije oba porta iz tog retka, zadano UDP 7882 i TCP 7881, pa ponovno otvorite stranicu.

### Token za DNS zapise

Dio {t:network.names} prikazuje se samo kad instalacija ima imena koja pokazuju izravno na njezinu javnu adresu: ime releja i domenu kad instalacija sama dobiva certifikat.

1. U Cloudflareu napravite API token s pravima Zone: Read i DNS: Edit za zonu tih imena.
2. Upišite ga u {t:network.token} i pritisnite {t:ai.save}.
3. Za zamjenu upišite novi token preko spremljenog i ponovno pritisnite {t:ai.save}.
4. Za uklanjanje pritisnite {t:network.forget}.

## Kako radi

{t:network.address} je adresa pod kojom internet vidi poslužitelj; instalacija je doznaje od javnog STUN poslužitelja pri svakom otvaranju stranice, a kad on ne odgovori, piše {t:network.unknown}. Zatim se spaja na TCP port sastanaka na toj adresi, kao preglednik izvana. Ako se spoji, piše {t:network.reached}. Zvuk i slika sastanka idu kroz poslužitelj instalacije, pa ih bez ta dva porta nitko izvan lokalne mreže ne prima, ni kroz vanjski relej. Unutar lokalne mreže sastanci rade i bez njih.

{t:network.relay} prikazuje ime releja za mreže koje puštaju van samo HTTPS, ili {t:network.noRelay}. Postavlja ga vlasnik poslužitelja naredbom `ponistra relay <ime>` uz prosljeđivanje TCP 443 i UDP 3478; `ponistra relay none` ga uklanja.

Token se prije spremanja provjerava kod Cloudflarea i čuva zapečaćen tajnim ključem instalacije; poslije se uz {t:network.kept} prikazuju samo njegova zadnja četiri znaka, a polje nudi {t:network.replace}. Svake dvije minute instalacija provjerava svoju javnu adresu i, kad se promijeni, usmjerava na nju zapise imena, a zapis koji ne postoji stvara. Kad to ne uspije, ispod polja stoji {t:network.refused} s Cloudflareovim odgovorom. Spremanje i uklanjanje tokena bilježe se u [dnevnik](help:admin/journal) kao {t:journal.setting.network_dns}.

[Zdravlje sustava](help:admin/health) provjerava oboje i javlja administratorima kad sastanci izvana ili DNS zapisi prestanu raditi.

## Ograničenja

- Provjera portova ide preko vlastite javne adrese. Usmjerivač koji ne vraća promet na vlastitu adresu pokazat će {t:network.unreached} iako izvana možda radi; tada provjerite pozivom s mobilne mreže.
- Provjerava se samo TCP port; UDP port poslužitelj sastanaka ne potvrđuje nepoznatom pošiljatelju, pa se prosljeđuju oba.
- Token radi samo kad zonu tih imena drži Cloudflare.
- {t:error.dns_token_refused} znači da Cloudflare token ne poznaje ili da je opozvan: napravite novi.

## Povezano

- [Zdravlje sustava](help:admin/health)
- [Administracija](help:admin/administration)
- [Gosti na sastanku](help:meetings/guests)
