# Stavke sefa

Stavka sefa je prijava s korisničkim imenom, lozinkom, jednokratnim kodom i adresama, bilješka sa slobodnim tekstom ili ključ pošte.

## Kako se koristi

### Nova stavka

1. U otvorenoj zbirci pritisnite {t:vault.newItem}. Za bilješku u izborniku ostalih radnji odaberite {t:vault.newNote}.
2. Pod {t:vault.kind} odaberite {t:vault.kind.login} ili {t:vault.kind.note}. Za {t:vault.kind.mailkey} vidite [Ključevi pošte u sefu](help:vault/mail-keys).
3. Upišite {t:tree.name}, a za prijavu i {t:vault.username}, {t:vault.password}, {t:vault.totp} i {t:vault.urls}.
4. Po želji upišite {t:vault.notes}.
5. Pritisnite {t:tree.create}.

### Generiranje lozinke

1. Uz polje lozinke pritisnite {t:vault.generate}.
2. Odaberite {t:vault.generator.length} te {t:vault.generator.upper}, {t:vault.generator.digits} i {t:vault.generator.symbols}.
3. Pritisnite {t:vault.generator.again} za drugu lozinku ili {t:vault.generator.use} da je upišete u polje.

### Rad s otvorenom stavkom

1. Odaberite stavku u popisu.
2. Uz polja pritisnite {t:vault.copyUsername}, {t:vault.copyPassword} ili {t:vault.copyTotp}.
3. Lozinku otkrivate pomoću {t:vault.show}, a skrivate pomoću {t:vault.hide}.
4. Uz svako polje {t:vault.url} pritisnite {t:vault.openUrl}.
5. Pritisnite {t:vault.edit} za izmjene, pa {t:tree.save}.
6. Pod {t:vault.history} su prijašnje lozinke stavke, svaka s mogućnošću kopiranja.

### Privitci

1. U otvorenoj stavci pritisnite {t:vault.attach} i odaberite datoteke. Dok traje, gumb prikazuje: {t:vault.attaching}
2. Pod {t:vault.attachments} pritisnite naziv privitka da ga preuzmete.
3. Za uklanjanje pritisnite {t:vault.removeAttachment}.

## Kako radi

Naziv, korisničko ime, lozinka, kod, adrese, bilješke i privitci šifriraju se u pregledniku. Na poslužitelj odlazi samo šifrirano, a privitak se otvara tek u pregledniku pri preuzimanju.

Kopirano se nakon 30 sekundi briše iz međuspremnika, osim ako ste u međuvremenu kopirali nešto drugo iz sefa. Jednokratni kod računa se u pregledniku i mijenja se svakih 30 sekundi, ako adresa ne odredi drugačije; uz njega piše koliko je sekundi ostalo. Za jednokratni kod upišite adresu `otpauth://` ili tajni ključ koji stranica prikazuje uz QR kod.

Kad promijenite lozinku, dosadašnja se sprema u prijašnje lozinke. Čuva se zadnjih 10. Ispod stavke piše {t:vault.changed} s vremenom zadnje izmjene.

Generirana lozinka zadano ima 20 znakova i sadrži velika slova, brojke i znakove. Uvijek ima mala slova i barem jedan znak svake odabrane vrste.

U dijeljenoj zbirci prikaz i kopiranje lozinke ili jednokratnog koda bilježe se u dnevniku zbirke. U Mojem sefu ne bilježi se ništa.

## Ograničenja

- Kad uneseno nije tajni ključ jednokratnih kodova, piše: {t:vault.totpInvalid}
- U zbirci u kojoj imate samo čitanje stavku ne možete mijenjati ni dodavati joj privitke.
- Duljina generirane lozinke je od 8 do 64 znaka.

## Povezano

- [Mape i premještanje](help:vault/folders)
- [Smeće sefa](help:vault/trash)
- [Dijeljene zbirke](help:vault/collections)
- [Ključevi pošte u sefu](help:vault/mail-keys)
