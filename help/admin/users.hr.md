# Korisnici

Na stranici {t:users.title} administrator otvara račune, mijenja ih, odjavljuje korisnike s uređaja, deaktivira i briše račune te izvozi podatke korisnika.

## Kako se koristi

### Novi korisnik

1. Otvorite {t:admin.title} i odaberite {t:users.title}.
2. Pritisnite {t:users.new}.
3. Upišite {t:users.firstName}, {t:users.lastName}, {t:auth.email} i {t:auth.password}.
4. Po potrebi označite {t:users.admin} i grupe korisnika, pa pritisnite {t:tree.create}.

### Izmjena računa

1. U retku korisnika otvorite izbornik i odaberite {t:users.edit}.
2. Promijenite podatke; polje {t:password.new} ostavite prazno da lozinka ostane ista.
3. Pritisnite {t:tree.save}.

### Uređaji i deaktivacija

1. U izborniku retka odaberite {t:devices.title} za popis preglednika u kojima je korisnik prijavljen.
2. Pritisnite {t:devices.end} uz jedan preglednik ili {t:devices.endAll}.
3. Za račun koji se više ne smije prijavljivati odaberite {t:users.deactivate} i potvrdite u dijalogu {t:users.deactivateTitle}
4. Deaktiviran račun vraćate s {t:users.activate}.

### Izvoz podataka

1. U izborniku retka odaberite {t:users.export}.
2. Potvrdite da ste to vi, ako Ponistra to zatraži.
3. Pričekajte da se datoteka pripremi; preglednik je zatim sprema pod adresom e-pošte korisnika.

### Brisanje korisnika

1. U izborniku retka odaberite {t:users.erase}.
2. U dijalogu {t:users.eraseTitle} pod {t:users.heir} odaberite korisnika koji preuzima dokumente i zajedničke sandučiće.
3. Pritisnite {t:users.erase} i potvrdite da ste to vi, ako Ponistra to zatraži.

## Kako radi

Popis pokazuje ime, adresu e-pošte, grupe i {t:users.lastLogin}, a uz ime oznake {t:users.admin} i {t:users.inactive}. Korisnik koji se nikad nije prijavio ima {t:users.never}.

Deaktiviran korisnik ne može se prijaviti i odjavljuje se sa svih uređaja. Njegovi dokumenti ostaju na računu i vraćaju se kad ga ponovno aktivirate.

Uz ime korisnika koji se prijavljuje kod izdavatelja ili dolazi iz imenika piše naziv tog izvora. Korisniku iz imenika adresa e-pošte, ime, lozinka i aktivnost mijenjaju se samo u imeniku, pa su u dijalogu {t:users.edit} ta polja i {t:users.deactivate} onemogućeni, kao i grupe koje dolaze od izvora. Vidi [Vanjska prijava i imenici](help:admin/sources).

Lozinka koju administrator postavi drugom korisniku njegov je put natrag nakon izgubljenog uređaja. Ako instalacija tom korisniku propisuje pristupni ključ, njegovi se pristupni ključevi pritom brišu, a novi dodaje pri sljedećoj prijavi.

Izvoz je jedna zip datoteka sa svime što instalacija drži o korisniku: podaci računa, svaki zapis koji ga imenuje kao JSON po vrsti podatka (pošta, kalendari, kontakti, zadaci, razgovori, komentari, uređaji, pristupi dokumentima i drugo), svaka poruka pošte kao datoteka .eml, fotografije njegovih kontakata, njegova vlastita pozadina za sastanke te njegovi dokumenti kao datoteke Ponistre i njegove datoteke kakve jesu, po mapama u kojima stoje. Popis dijelova nalazi se u datoteci manifest.json. Lozinke, ključevi i tokeni ne izvoze se, kao ni postavke instalacije. Sadržaj sefa zaključan je u pregledniku, pa ga korisnik izvozi sam iz sefa. Pripremljena datoteka ostaje na poslužitelju 1 sat.

Brisanje je konačno. Briše se račun i sve što pripada samo njemu: kopije pošte u Ponistri (poruke na poslužitelju pošte ostaju), kalendari, kontakti, zadaci, osobni sef, pristupni ključevi, lozinke aplikacija i prijave na svim uređajima. Poruke u razgovorima i komentari koje je pisao drugima ostaju, bez imena autora. Dokumenti i mape kojima je bio jedini vlasnik, uključujući one u smeću, prelaze u jednu mapu na vrhu dokumenata korisnika kojeg ste odabrali, nazvanu po izbrisanom korisniku; njegove bilješke, poveznice i ploče ondje postaju obične mape. Mape tvrtke kojima je bio jedini vlasnik ostaju na svom mjestu, a odabrani korisnik postaje njihov vlasnik. Isto vrijedi za [zajedničke sandučiće](help:mail/mailboxes) kojima je bio jedini vlasnik: sandučić ostaje kakav jest, a odabrani korisnik postaje njegov vlasnik. Ono što ima i drugog vlasnika ostaje tom vlasniku, a dijeljenja s drugima ostaju kakva jesu. Imena u prijedlozima izmjena unutar dokumenata dio su sadržaja dokumenta i ostaju.

Dodavanje, promjena i brisanje korisnika upisuju se u [dnevnik](help:admin/journal), kao i prekid prijava na njegovim uređajima.

## Ograničenja

- Vlastitom računu ne možete oduzeti administratorska prava, deaktivirati ga ni izbrisati.
- Dokumente i sandučiće može preuzeti samo drugi aktivni korisnik; inače se javlja: {t:error.invalid_heir}
- Korisnik koji je jedini vlasnik zajedničke zbirke sefa ili zbirke tvrtke ne može se izbrisati dok zbirka ne dobije drugog vlasnika, jer je njezin ključ zaključan samo za članove: {t:error.collection_owner}
- Korisnik pod zakonskim čuvanjem ne može se izbrisati ({t:error.held}), kao ni korisnik čija je pošta još u roku čuvanja ({t:error.retained}); vidi [Čuvanje podataka](help:admin/retention).
- Izvoz i brisanje može pokrenuti samo administrator.
- Adresa e-pošte mora biti jedinstvena u instalaciji.
- Otvaranje, izmjena i brisanje računa te izvoz podataka mogu tražiti potvrdu da ste to vi.

## Povezano

- [Grupe](help:admin/groups)
- [Pravila prijave](help:admin/policy)
- [Vanjska prijava i imenici](help:admin/sources)
- [Oporavak sefova](help:admin/recovery)
