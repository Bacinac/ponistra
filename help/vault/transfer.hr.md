# Uvoz i izvoz sefa

Lozinke iz drugog upravitelja lozinki ili preglednika unosite u zbirku sefa, a zbirku izvozite u datoteku koju čita svaki upravitelj lozinki.

## Kako se koristi

### Uvoz

1. Otvorite zbirku u koju uvozite i u izborniku ostalih radnji odaberite {t:vault.import}
2. Pritisnite {t:vault.importChoose} i odaberite izvoz drugog upravitelja.
3. Dijalog prikazuje prepoznati oblik ({t:vault.format.bitwarden}, {t:vault.format.chrome}, {t:vault.format.firefox}, {t:vault.format.keepassxc} ili {t:vault.format.keepass}), {t:vault.importItems} i {t:vault.importSkipped}.
4. Pritisnite {t:vault.importDo}.
5. Nakon uvoza obrišite datoteku s uređaja.

### Izvoz

1. Otvorite zbirku i u izborniku ostalih radnji odaberite {t:vault.export}
2. Pročitajte upozorenje i pritisnite {t:vault.exportDo}.
3. Ako Ponistra zatraži, potvrdite da ste to vi. Preglednik sprema datoteku s nazivom zbirke.

## Kako radi

Datoteka se čita u pregledniku i ne šalje se poslužitelju. Prijave i bilješke šifriraju se u pregledniku i ulaze u otvorenu zbirku, zajedno s mapama u kojima su bile. Bitwarden se čita iz izvoza JSON ili CSV, a ostali iz izvoza CSV. Kartice i identiteti iz Bitwardena se preskaču.

Izvoz je datoteka u Bitwardenovu obliku JSON, s lozinkama u čitljivom obliku i s mapama zbirke. Privitci se ne izvoze. Ključ pošte izvozi se kao bilješka: tajni ključ i certifikati u obliku PEM, a ključ OpenPGP kao tekstni blok OpenPGP, pa ga drugi alati mogu ponovno učitati. Kao i lozinke, tajni ključ u izvozu nije šifriran. Svaki izvoz bilježi se u dnevniku dijeljene zbirke.

## Ograničenja

- Izvoz smije samo vlasnik zbirke, a uvoz tko u njoj može uređivati.
- Kad je datoteka šifrirani izvoz, piše: {t:vault.unreadable.encrypted}
- Kad datoteka nije prepoznata, piše: {t:vault.unreadable.unknown}
- Izvezena datoteka nije zaštićena. Čuvajte je kao sam sef i obrišite je čim je uvezete.

## Povezano

- [Sef](help:vault/overview)
- [Dijeljene zbirke](help:vault/collections)
