# Dnevnik

Dnevnik bilježi što se događalo s instalacijom u cjelini: prijave i neuspjele prijave, promjene korisnika, grupa i ključeva, administratorske postavke i probleme koje je Ponistra sama našla.

## Kako se koristi

1. Otvorite {t:admin.title} i odaberite {t:journal.title}.
2. Upisi stoje od najnovijeg prema starijima. Uz svaki piše {t:log.when}, {t:log.who}, {t:log.what} i {t:journal.address} s koje je došao zahtjev.
3. Pod {t:journal.group} odaberite {t:journal.group.all}, {t:journal.group.sign_ins}, {t:journal.group.accounts}, {t:journal.group.settings} ili {t:journal.group.health}.
4. Pod {t:journal.person} odaberite korisnika da vidite samo ono što je on napravio ili što je napravljeno njemu, ili {t:journal.everyone}.
5. Za upise starije od prikazanih pritisnite {t:journal.more} na dnu popisa.

Dok nema nijednog upisa koji odgovara odabiru, piše {t:journal.none}

## Kako radi

### Što se upisuje

Pod {t:journal.group.sign_ins}: {t:journal.kind.signed_in} (lozinkom, pristupnim ključem, {t:journal.way.oidc} ili {t:journal.way.saml}, a zadržite li pokazivač na retku, vidi se preglednik), {t:journal.kind.sign_in_failed} s adresom e-pošte koja je upisana, {t:journal.kind.locked_out}, {t:journal.kind.signed_out}, {t:journal.kind.sessions_ended} (kada korisnik ili administrator odjavi uređaje) i {t:journal.kind.application_signed_in}, kada se netko kroz Ponistru prijavi u drugu aplikaciju.

Pod {t:journal.group.accounts}: {t:journal.kind.installed}, {t:journal.kind.user_added}, {t:journal.kind.user_changed} s onim što je promijenjeno (ime, adresa e-pošte, uloga administratora, aktivnost, lozinka, grupe), {t:journal.kind.user_erased} s nasljednikom dokumenata, {t:journal.kind.group_added}, {t:journal.kind.group_renamed}, {t:journal.kind.group_removed}, {t:journal.kind.password_changed}, {t:journal.kind.passkey_added}, {t:journal.kind.passkey_removed}, {t:journal.kind.app_password_added} i {t:journal.kind.app_password_removed}.

Pod {t:journal.group.settings}: {t:journal.kind.policy_changed}, {t:journal.kind.application_added}, {t:journal.kind.application_changed}, {t:journal.kind.application_removed}, {t:journal.kind.application_secret}, {t:journal.kind.provider_added}, {t:journal.kind.provider_changed}, {t:journal.kind.provider_removed}, {t:journal.kind.provider_secret} i {t:journal.kind.setting_changed}, uz ime postavke: {t:journal.setting.ai}, {t:journal.setting.ai_monthly}, {t:journal.setting.speech}, {t:journal.setting.mail_client}, {t:journal.setting.mail_opened}, {t:journal.setting.push}, {t:journal.setting.resource}, {t:journal.setting.hours}, {t:journal.setting.workdays}, {t:journal.setting.closures}, {t:journal.setting.offsite}, {t:journal.setting.offsite_kit}, {t:journal.setting.retention} i {t:journal.setting.legal_hold}.

Pod {t:journal.group.health}: {t:journal.kind.problem} i {t:journal.kind.resolved}, koje upisuje sama Ponistra, pa je ona navedena kao korisnik.

### Čuvanje i privatnost

Dnevnik se čuva godinu dana, starije upise briše prva sljedeća prijava. Lozinke, ključevi i tajne nikad se ne upisuju. Kada se korisnik izbriše, s njim se brišu njegove prijave, odjave, ključevi i neuspjele prijave pod njegovom adresom, a ono što je kao administrator napravio drugima ostaje bez njegova imena. Izvoz podataka osobe nosi i njezine upise iz dnevnika.

Dnevnik se osvježava sam čim se dogodi nešto novo. Što je tko otvarao, preuzimao i dijelio u dokumentima i mapama, vidi se u zapisniku pristupa svakog dokumenta, a sef ima svoj zapisnik.

## Ograničenja

- Dnevnik otvara samo administrator.
- Promjene koje se rade naredbama na poslužitelju, ne kroz Ponistru, ne upisuju se.
- Adresa je ona koju Ponistri predaje posrednik ispred nje; iza posrednika koji je ne predaje, upisuje se adresa samog posrednika.

## Povezano

- [Stanje sustava](help:admin/health)
- [Korisnici](help:admin/users)
- [Pravila prijave i dijeljenja](help:admin/policy)
