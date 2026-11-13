# Skeniranje

Stranice papira snimljene mobitelom Ponistra izravna i spremi kao jedan PDF s prepoznatim tekstom, u mapu ili kao privitak poruke.

## Kako se koristi

### U mapu

1. Otvorite mapu, pritisnite {t:create.new} i odaberite {t:create.scan}
2. Na mobitelu pritisnite {t:scan.take}: otvara se kamera i snima jednu stranicu. Na računalu, ili za fotografije koje već imate, pritisnite {t:scan.add}
3. Ponistra nađe rubove stranice i ocrta ih na fotografiji. Ako rub nije dobar, povucite kut na pravo mjesto. S tipkovnicom kut odaberite tabulatorom i pomičite ga strelicama.
4. {t:scan.whole} uzima cijelu fotografiju, bez obrezivanja.
5. Ponovite za svaku sljedeću stranicu. Sličice ispod fotografije pokazuju stranice redom: pritiskom na sličicu otvara se ta stranica, a {t:scan.remove} je izbacuje.
6. Naziv u polju {t:tree.name} unaprijed je današnji datum; promijenite ga po želji.
7. Pritisnite {t:scan.save}. Nova PDF datoteka otvara se kad je gotova.

### Kao privitak poruke

1. U poruci koju pišete pritisnite {t:mail.scan}
2. Snimite stranice kao gore i pritisnite {t:scan.attach}. PDF se dodaje među privitke poruke, a nazvan je kao u polju {t:tree.name}.

## Kako radi

Svaka fotografija učitava se na poslužitelj čim je snimljena ili dodana, a dok se traže rubovi, na njoj se vrti oznaka. Rub stranice traži se kao najveća svijetla ploha na fotografiji, pa se papir najbolje nađe na tamnoj podlozi.

Spremanjem se svaka stranica izravna po svojim kutovima i papir se izjednači do bijelog, tako da nestanu sjene i neravnomjerno svjetlo. Boje na stranici ostaju. Stranice se slažu u PDF redom kojim su snimljene, a dulja strana svake stranice duga je kao kod A4, jer fotografija ne pokazuje veličinu papira. Zatim se tekst prepoznaje na hrvatskom i engleskom jeziku, pa je PDF odmah pretraživ. Dok se PDF izrađuje, piše {t:job.scan}.

PDF u mapi vide svi koji vide mapu. Fotografije se ne čuvaju: koje nisu postale PDF brišu se same nakon sat vremena.

## Ograničenja

- U jedan PDF stane najviše 100 stranica.
- Fotografija mora biti JPEG, PNG ili WebP. Kamera mobitela snima JPEG.
- Za spremanje u mapu potrebno je pravo uređivanja mape; bez njega je {t:create.scan} onemogućen.
- {t:error.invalid_corners} Kutovi se ne smiju prekrižiti ni stisnuti u premalu plohu; povucite ih natrag na rubove stranice.
- {t:error.unknown_file} Javlja se kad je od snimanja stranice prošlo više od sat vremena; snimite je ponovno.
- {t:error.unreadable} Javlja se za fotografiju koju nije moguće otvoriti; snimite je ponovno.

## Povezano

- [Prepoznavanje teksta](help:pdf/ocr)
- [PDF datoteke](help:pdf/viewer)
- [Pisanje poruke](help:mail/composing)
