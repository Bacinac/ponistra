# Ključevi pošte u sefu

Ključ pošte u sefu potpisuje Vaše poruke i otvara šifrirane poruke koje Vam stignu, S/MIME certifikat ili ključ OpenPGP.

## Kako se koristi

### Učitavanje postojećeg ključa

1. U otvorenoj zbirci u izborniku ostalih radnji odaberite {t:vault.newMailKey}. Isto možete pritiskom na {t:vault.newItem} i odabirom {t:vault.kind.mailkey}.
2. Pritisnite {t:vault.mailkey.fromFile} i odaberite datoteku: certifikat S/MIME kao `.p12` ili `.pfx`, ili tajni ključ OpenPGP kao `.asc`.
3. Upišite {t:vault.mailkey.password}, lozinku kojom je datoteka zaštićena. Nezaštićen ključ OpenPGP učitava se s praznim poljem.
4. Pritisnite {t:vault.mailkey.open}. Ispod se prikazuju vrsta ključa, adrese, otisak i datum do kojeg vrijedi.
5. Po želji promijenite {t:tree.name}, pa pritisnite {t:tree.create}.

### Novi ključ OpenPGP

1. Odaberite {t:vault.newMailKey}.
2. Pritisnite {t:vault.mailkey.make}.
3. Pod {t:vault.mailkey.address} provjerite adresu, zadano je adresa Vašeg korisničkog računa.
4. Pritisnite {t:vault.mailkey.create}, pa {t:tree.create}.

### Otvoren ključ

U otvorenoj stavci piše je li to {t:vault.mailkey.smime} ili {t:vault.mailkey.pgp}, za koje adrese vrijedi, njegov otisak i {t:vault.mailkey.expires}, odnosno {t:vault.mailkey.expired}. Pritiskom na {t:vault.mailkey.public} preuzimate javni dio, certifikat `.cer` ili ključ `.asc`, koji šaljete onima koji Vam žele pisati šifrirano.

## Kako radi

Datoteka se otvara u pregledniku. Sef čuva tajni ključ šifriran kao i lozinke, pa ga poslužitelj nikad ne vidi.

Kad spremite novi ključ, njegov javni dio objavljuje se u Ponistri za svaku adresu koju nosi. Tako Vam kolege u istoj instalaciji mogu slati šifrirane poruke, a Vaše poslane šifrirane poruke šifriraju se i Vama, pa ih možete ponovno pročitati.

Novi ključ OpenPGP koristi Curve25519, koji čitaju GnuPG, Thunderbird i ostali alati OpenPGP. Zadano ne istječe.

Ključ u dijeljenoj zbirci mogu koristiti svi njezini članovi, primjerice za zajednički sandučić.

## Ograničenja

- Ključ se nakon spremanja ne mijenja. Za novi certifikat dodajte novu stavku, a stari izbrišite kad Vam više ne treba za stare poruke.
- Kad datoteka nije PKCS #12, piše: {t:smime.notPkcs12}
- Kad je lozinka kriva, piše: {t:smime.wrongPassword} ili {t:pgp.wrongPassphrase}
- Starije datoteke `.p12` zaštićene su šifriranjem RC2 ili 3DES, koje preglednik ne zna otvoriti. Tada piše: {t:smime.oldPkcs12} U Windowsima pri izvozu certifikata odaberite šifriranje AES256-SHA256.
- Kad u datoteci nema tajnog ključa, piše: {t:smime.noKey}
- Kad datoteka OpenPGP nema tajni ključ, nego samo javni, piše: {t:pgp.notPrivate} Javni ključ druge osobe učitava se u postavkama Pošte, vidite [Šifrirana i potpisana pošta](help:mail/encrypted).

## Povezano

- [Šifrirana i potpisana pošta](help:mail/encrypted)
- [Stavke sefa](help:vault/items)
- [Uvoz i izvoz sefa](help:vault/transfer)
