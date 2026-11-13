# Sef

Sef čuva vaše lozinke, jednokratne kodove i bilješke šifrirane u pregledniku, tako da ih poslužitelj ni administrator ne mogu pročitati.

## Kako se koristi

![Otključan sef s otvorenom stavkom](shot:vault-open)

### Izrada sefa

1. U lijevom stupcu Dokumenata odaberite {t:vault.title} ili upišite njegov naziv u kutiju za pretragu. Prvi put stranica prikazuje {t:vault.setup}.
2. Upišite {t:vault.password.new}, barem 12 znakova, i ponovite je pod {t:vault.password.again}.
3. Pritisnite {t:vault.make}.
4. Otvara se {t:vault.code}. Pritisnite {t:health.kit.copy} ili {t:health.kit.download} i spremite kod izvan Ponistre.
5. Pritisnite {t:vault.codeKept}.

### Otključavanje i zaključavanje

1. Zaključan sef prikazuje {t:vault.locked}.
2. Upišite {t:vault.password.vault} i pritisnite {t:vault.unlock}, ili pritisnite {t:vault.withPasskey} ako ste ga uključili.
3. Za zaključavanje pritisnite {t:vault.lock} na dnu lijevog stupca.
4. Vrijeme nakon kojeg se sef sam zaključava birate u {t:vault.settings}, pod {t:vault.idle}: {t:vault.idle.5}, {t:vault.idle.15} ili {t:vault.idle.60}.

### Kretanje po sefu

1. U lijevom stupcu {t:vault.mine} drži stavke koje vidite samo vi.
2. Pod {t:vault.shared} su zbirke koje dijelite s drugima, a pod {t:tree.company} zbirke koje vam je dala tvrtka.
3. Mape otvorene zbirke prikazuju se ispod nje, s brojem stavki.
4. Obrisane stavke su pod {t:trash.title}.
5. Upišite riječ u {t:vault.search}. Pretraga obuhvaća naziv, korisničko ime, adrese i bilješke cijele zbirke, ne samo otvorene mape.

## Kako radi

Sve što je u sefu šifrira se u vašem pregledniku prije nego što ode na poslužitelj, a otvara se tek u pregledniku nakon otključavanja. Ključ sefa izvodi se iz lozinke sefa, koja nije lozinka za prijavu i ne šalje se poslužitelju.

Otključan sef ostaje otvoren dok radite bilo gdje u Ponistri. Zaključava se kad pritisnete {t:vault.lock}, kad se odjavite, kad ponovno učitate stranicu i kad za odabrano vrijeme ne pritisnete nijednu tipku ni ne kliknete. Zadano je 15 minuta, a izbor se pamti u tom pregledniku.

Kod za oporavak otvara sef ako zaboravite lozinku. Kasnije ga možete ponovno prikazati ili zamijeniti novim u [postavkama sefa](help:vault/recovery).

U praznoj zbirci piše: {t:vault.empty} U praznoj mapi piše: {t:vault.folderEmpty} Kad pretraga ništa ne nađe, piše: {t:vault.noMatch}

## Ograničenja

- Lozinku sefa nitko ne može vratiti. Bez nje, koda za oporavak i pristupnog ključa sef se ne može otvoriti, osim ako je tvrtka uključila oporavak sefova.
- Kad lozinke nisu jednake, piše: {t:vault.password.differs}
- Kad lozinka nije točna, piše: {t:vault.wrongPassword}
- {t:vault.noPrf} Pristupni ključ s drugog uređaja ili iz drugog upravitelja možda to podržava.

## Povezano

- [Stavke sefa](help:vault/items)
- [Dijeljene zbirke](help:vault/collections)
- [Lozinka, kod i pristupni ključevi sefa](help:vault/recovery)
