# Mrežne lokacije

Mrežna lokacija je mapa na poslužitelju, zajedno s računom kojim se Ponistra na njega prijavljuje; dodaje se u postavkama, a njezine se datoteke otvaraju u Dokumentima.

## Kako se koristi

### Dijeljena mapa (SMB)

1. U postavkama otvorite {t:locations.settings} i pritisnite {t:locations.add}.
2. Pod {t:explorer.kind} ostavite {t:locations.kind.smb}.
3. Upišite {t:tree.name} i {t:locations.address} u obliku `\\poslužitelj\mapa`, po želji s podmapom.
4. Upišite {t:locations.username} (za domenu `DOMENA\korisnik`) i {t:locations.auth.password}. {t:locations.port} upisujete samo ako nije 445.
5. Pritisnite {t:tree.save} ili {t:tree.cancel}.

### SSH poslužitelj (SFTP)

1. Pritisnite {t:locations.add} i pod {t:explorer.kind} odaberite {t:locations.kind.sftp}.
2. Upišite {t:tree.name}, {t:locations.host} i, ako nije 22, {t:locations.port}.
3. Pod {t:locations.path} upišite mapu na poslužitelju od koje lokacija počinje; prazno znači početnu mapu računa.
4. Upišite {t:locations.username} i pod {t:locations.auth} odaberite {t:locations.auth.password} ili {t:locations.auth.key}.
5. Ako se do poslužitelja dolazi samo preko drugoga, upišite ga pod {t:locations.jump} u obliku `korisnik@poslužitelj:port`.
6. Pritisnite {t:tree.save}.
7. Uz prijavu ključem ispod lokacije se pojavljuje javni ključ. Pritisnite {t:locations.copyKey} i dodajte ga u `~/.ssh/authorized_keys` računa na poslužitelju, a ako lokacija ide preko drugog poslužitelja, i računa na njemu.

### Izmjena, dijeljenje i uklanjanje

1. U retku lokacije otvorite izbornik radnji.
2. {t:locations.edit} otvara ista polja; lozinka se mijenja samo ako upišete novu.
3. {t:access.share} otvara popis pristupa: dodajte osobu, grupu ili sve korisnike i odaberite {t:access.role.read}, {t:access.role.edit} ili {t:access.role.own}.
4. {t:locations.remove} uklanja lokaciju nakon potvrde.

Naziv lokacije u popisu otvara njezine [datoteke](help:documents/network).

## Kako radi

Pri spremanju lokacije s lozinkom Ponistra se odmah prijavljuje na poslužitelj, pa se lokacija s krivom adresom ili prijavom ne sprema. Lokacija s ključem sprema se bez prijave, jer ključ vrijedi tek kad ga dodate na poslužitelj.

Lozinka i privatni ključ čuvaju se šifrirani tajnim ključem instalacije i nikad se ne pokazuju, ni vlasniku. Ključ izrađuje Ponistra, za svaku lokaciju poseban, i njegov privatni dio ne napušta instalaciju.

Pri prvoj prijavi na SSH poslužitelj Ponistra pamti ključ kojim se poslužitelj predstavio. Predstavi li se poslije drugim, veza se odbija dok vlasnik ne spremi lokaciju ponovno; izmjena poslužitelja, porta ili poslužitelja za prolaz pamti ključ iznova.

Svi s kojima je lokacija podijeljena rade na poslužitelju istim računom, onim iz lokacije. Uloga u Ponistri određuje samo smiju li čitati ili i mijenjati, a postavke lokacije vidi i mijenja samo vlasnik. Kome je lokacija podijeljena, u ovom popisu umjesto izbornika vidi ime vlasnika.

Uklanjanjem lokacija nestaje svima, a datoteke na poslužitelju ostaju netaknute.

## Ograničenja

- Tko smije dodati lokaciju određuje administrator. Kad vama nije dopušteno, gumba {t:locations.add} nema, a pokušaj javlja {t:error.locations_off} Lokacije podijeljene s vama i dalje otvarate.
- Dodavanje, izmjena, dijeljenje i uklanjanje mogu tražiti [potvrdu da ste to vi](help:account/confirm).
- Poslužitelj mora biti dostupan s poslužitelja na kojem radi Ponistra, ne s vašeg uređaja. Inače piše {t:error.location_unreachable} ili {t:error.location_host_unknown}
- {t:error.location_login} znači krivo korisničko ime ili lozinku, ili ključ koji još nije dodan na poslužitelj.
- {t:error.location_sftp_missing} znači da SSH poslužitelj ne dopušta prijenos datoteka tom računu.
- {t:error.location_not_found} znači da upisane mape na poslužitelju nema.
- {t:error.invalid_jump} i {t:error.invalid_location_name} opisuju polje koje treba ispraviti.

## Povezano

- [Datoteke na mreži](help:documents/network)
- [Dijeljenje](help:documents/sharing)
- [Potvrda da ste to vi](help:account/confirm)
