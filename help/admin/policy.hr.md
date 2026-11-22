# Pravila prijave i dijeljenja

Administrator određuje smije li se i mora li se prijavljivati pristupnim ključem, traži li prijava lozinkom drugi korak, smije li se datoteka s računala otvoriti bez prijave, tko smije izraditi poveznicu za nekoga izvan instalacije i tko smije dodati mrežnu lokaciju.

## Kako se koristi

1. Na stranici {t:users.title}, u odjeljku {t:policy.title}, pod {t:policy.passkeys} odaberite {t:policy.passkeys.off}, {t:policy.passkeys.nobody}, {t:policy.passkeys.administrators} ili {t:policy.passkeys.everyone}.
2. Uključite ili isključite {t:policy.secondFactor} i {t:policy.opening}.
3. U odjeljku {t:policy.outside.title}, pod {t:policy.outside}, odaberite {t:policy.outside.nobody}, {t:policy.outside.administrators} ili {t:policy.outside.everyone}.
4. U odjeljku {t:policy.locations.title}, pod {t:policy.locations}, odaberite isto.

## Kako radi

Uz {t:policy.passkeys.off} stranica prijave ne nudi pristupni ključ i prijava njime se odbija; korisnici se prijavljuju lozinkom ili kod izdavatelja organizacije. Uz {t:policy.passkeys.nobody} svatko bira hoće li dodati ključ.

Pravilo o pristupnom ključu vrijedi od sljedeće prijave. Tko mora imati pristupni ključ, lozinkom se prijavljuje samo dok ga ne doda, a nakon toga samo ključem. Korisnik bez ključa nakon prijave lozinkom najprije dodaje ključ.

Uz {t:policy.secondFactor} prijava lozinkom traži i kôd iz [aplikacije za autentifikaciju](help:account/authenticator) ili pristupni ključ, kad prijava ključem nije isključena. Korisnik koji nema ni jedno ni drugo nakon prijave lozinkom najprije dodaje jedno od njih. Korisnik koji je aplikaciju dodao sam, kôd daje i kad je ovo isključeno. Prijava kod izdavatelja organizacije ne traži drugi korak u Ponistri, jer ga traži izdavatelj prema svom pravilu.

Ako takav korisnik izgubi uređaj, administrator mu pod {t:users.edit} postavlja novu lozinku; time se brišu njegova aplikacija za autentifikaciju i, kad mu je ključ obavezan ili je drugi korak uključen, pristupni ključevi, a novi dodaje pri sljedećoj prijavi.

Uz {t:policy.opening} datoteku koju netko otvori s računala instaliranom aplikacijom, a nije prijavljen, Ponistra prikazuje samo za čitanje, kao privremeni dokument koji nestaje kad se prozor zatvori, najkasnije za sat vremena; tko se iz tog prozora prijavi, preuzima je i sprema u mapu. PDF se i bez ovoga čita u pregledniku i ne šalje poslužitelju. S jedne adrese može se tako otvoriti najviše 30 datoteka na sat, svaka do 100 MB.

Pravilo dijeljenja određuje tko smije izraditi poveznicu kojom netko bez računa u instalaciji otvara ploču. Uz {t:policy.outside.nobody} prestaju vrijediti i sve već izrađene poveznice.

Pravilo mrežnih lokacija određuje tko smije dodati [mrežnu lokaciju](help:documents/locations), dakle upisati poslužitelj i račun kojim se Ponistra na njega prijavljuje. Već dodane lokacije ostaju i dalje se otvaraju, i onima s kojima su podijeljene.

Svaka promjena pravila upisuje se u [dnevnik](help:admin/journal).

## Ograničenja

- Promjena pravila može tražiti potvrdu da ste to vi.
- Korisnik kojemu je ključ obavezan ne može obrisati svoj posljednji pristupni ključ.
- Dok je drugi korak uključen, korisnik ne može ukloniti onaj koji mu je jedini: aplikaciju za autentifikaciju bez pristupnog ključa, ni posljednji pristupni ključ bez aplikacije.

## Povezano

- [Aplikacija za autentifikaciju](help:account/authenticator)
- [Korisnici](help:admin/users)
