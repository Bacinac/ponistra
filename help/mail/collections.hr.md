# Zbirke

Zbirka skuplja poruke koje odaberete, poput računa, slaže njihove privitke u mapu po mjesecima i jednom mjesečno ih šalje s tablicom iznosa.

## Kako se koristi

### Nova zbirka

1. Otvorite Postavke i odaberite {t:collections.title}.
2. Pritisnite {t:collections.new}.
3. Upišite {t:collections.name}. Po njemu se zove mapa zbirke i predmet poruke.
4. Pod {t:collections.takes} odredite koje poruke zbirka uzima:
   - {t:collections.accounts}: računi e-pošte s kojih uzima, ako ih imate više;
   - {t:collections.senders}: adrese ili domene odvojene zarezom;
   - {t:collections.words}: riječi odvojene zarezom;
   - {t:collections.attached};
   - {t:collections.recognise}, ako želite da zbirka zadrži samo račune;
   - {t:collections.since}: dan od kojeg zbirka uzima i ranije primljenu poštu.
5. Pod {t:collections.goes} upišite {t:collections.to} i, ako imate više računa, {t:collections.from}. Bez odabira poruka ide s {t:collections.fromDefault}.
6. Odaberite {t:collections.day} i {t:collections.hour} u kojem zbirka šalje prethodni mjesec, a pod {t:collections.currency} oznaku valute u kojoj tablica daje i svaki iznos, primjerice EUR. Bez oznake iznosi se ne preračunavaju.
7. Pod {t:collections.sends} odaberite {t:collections.draft} ili {t:collections.send}.
8. Po želji upišite {t:collections.text}.
9. Pritisnite {t:tree.save}. Ako ste uključili prepoznavanje, Ponistra najprije pita za pristanak: {t:collections.consent} Pristanak dajete s {t:collections.consentGive}, a vrijedi dok prepoznavanje ne isključite.

### Pregled mjeseci

Ispod svake zbirke stoji zadnjih 13 mjeseci. Uz mjesec stoji koliko je poruka {t:collections.kept}, koliko ih {t:collections.waiting} na čitanje, koliko ih {t:collections.passed} i koliko ih je {t:collections.missed}, te kada je mjesec poslan ili kada će biti.

1. Pritisnite ikonu mape uz mjesec da otvorite njegove datoteke, ili {t:collections.openFolder} uz naziv zbirke za cijelu zbirku.
2. Pritisnite {t:collections.sendNow} za mjesec koji je {t:collections.notSent}.
3. Pritisnite {t:collections.sendAgain} i potvrdite da ponovno pošaljete već poslan mjesec, sa svime što je sada u njegovoj mapi. Dok poruka nastaje, uz mjesec stoji {t:collections.sending}.
4. Pritisnite mjesec da vidite njegove stavke: datum, dobavljača, iznos i iznos u valuti zbirke. Uz račun bez datoteke stoji {t:collections.unfiled}, a pritisak na tu oznaku otvara poruku.
5. Ako je banka naplatila drugačiji iznos, upišite ga u polje {t:collections.converted} uz stavku i pritisnite Enter. Uz iznos tada stoji {t:collections.byHand}. Obrišite ga da se vrati iznos po tečaju.

### Dodavanje datoteke rukom

1. Pritisnite ikonu mape uz mjesec.
2. Učitajte PDF računa u tu mapu, primjerice račun preuzet s weba.
3. Zbirka ga uzme unutar minute i pridruži stavci kojoj pripada ili od njega napravi novu.

### Dodavanje poruke rukom

1. Otvorite poruku u svom sandučiću.
2. U izborniku poruke odaberite {t:collections.add}
3. Odaberite {t:collections.into} i pritisnite {t:collections.addConfirm}. Ako još nemate zbirku, dijalog piše {t:collections.none} i vodi na {t:collections.new}.

### Promjena, isključivanje i brisanje

1. Pritisnite {t:collections.edit} uz zbirku, promijenite što treba i pritisnite {t:tree.save}, ili {t:tree.cancel} da odustanete.
2. Isključite {t:collections.active} da zbirka privremeno ne uzima ni ne šalje. Uz naziv tada stoji {t:collections.paused}.
3. Pritisnite {t:collections.remove} i potvrdite. {t:collections.removeKeeps}

## Kako radi

Zbirka radi na poslužitelju, pa skuplja i šalje i kad su svi vaši uređaji isključeni. Novu poštu pogleda svake minute, a kad je spremite ili promijenite što uzima, odmah pregleda i poštu od dana u {t:collections.since}.

Kad zbirka zadrži račun bez datoteke, šalje obavijest na uređaje na kojima ste dopustili obavijesti. Pritisak na obavijest otvara poruku, u kojoj obično piše gdje se račun preuzima.

Datoteku koju stavite u mapu mjeseca zbirka pročita kao račun. Ako postoji zadržana stavka istog iznosa i valute s datumom unutar 3 dana, datoteka joj se pridruži, najprije stavci bez datoteke. Tako se račun i potvrda o plaćanju pridruže istoj stavci. Inače datoteka postaje nova stavka. Bez prepoznavanja nova stavka nosi naziv datoteke i nema iznos.

Iznos u valuti zbirke računa se po referentnom tečaju Europske središnje banke koji je objavljen zadnji dan prije datuma računa. To je tečaj koji na taj dan primjenjuje Hrvatska narodna banka. Iznos koji upišete rukom zbirka nikad ne mijenja. Kad promijenite valutu zbirke, iznosi po tečaju računaju se ponovno.

Poruka mora zadovoljiti svaki uvjet koji ste upisali. Unutar jednog uvjeta dovoljno je jedno: bilo koji od pošiljatelja i bilo koja od riječi u predmetu. Domena uzima i svoje poddomene. Poslana pošta, skice, smeće i neželjena pošta se ne uzimaju.

Svaka poruka pripada mjesecu u kojem je stigla, po vremenu instalacije. Mapa zbirke stoji na vrhu vaših dokumenata, a u njoj je za svaki mjesec mapa nazvana godinom i mjesecom. Privitci poruke ulaze u mapu mjeseca s datumom ispred naziva, a ista datoteka iz više poruka samo jednom. Obrisanu mapu zbirka napravi ponovno.

Bez prepoznavanja zbirka zadrži svaku poruku koju uzme: kao dobavljača upiše ime ili domenu pošiljatelja, a kao datum dan primitka. S prepoznavanjem model umjetne inteligencije čita tekst poruke i tekst njezinih privitaka, odlučuje je li riječ o računu i iščita dobavljača, datum, iznos i valutu. Poruka koja nije račun dobiva oznaku {t:collections.passed} i njezini privitci ne ulaze u mapu. Zbirka pričeka do 30 minuta da Ponistra pročita tekst PDF privitka. Svako čitanje bilježi se u potrošnji umjetne inteligencije. Poruku koju dodate rukom zbirka zadrži uvijek, a model samo iščita njezine podatke.

Mjesec odlazi na odabrani dan i sat sljedećeg mjeseca, kad su pročitane sve poruke koje čekaju, a najkasnije 6 sati poslije. Poruka u predmetu ima naziv zbirke, mjesec i godinu. U tijelu je vaš tekst, tablica s dobavljačem, datumom, iznosom, valutom, iznosom u valuti zbirke i datotekama, zbroj po valuti, ukupno u valuti zbirke i potpis računa. Privitci su sve datoteke u mapi mjeseca u tom trenutku, i one koje ste sami dodali, te ista tablica kao radna knjiga. Tablica ostaje i kao dokument u mapi mjeseca, a ponovno slanje je osvježi.

Uz {t:collections.draft} poruka čeka među vašim skicama da je pregledate i pošaljete. Uz {t:collections.send} odlazi sama i ostaje u poslanoj pošti.

Mjeseci kojima je dan slanja prošao prije nego što ste napravili zbirku ne šalju se sami. Za njih stoji {t:collections.notSent} dok ih ne pošaljete gumbom. Mjesec bez ijedne poruke i datoteke ne šalje se.

Stranica se osvježava sama kad zbirka uzme ili pošalje nešto, na svakom vašem uređaju.

## Ograničenja

- Zbirka uzima samo vašu poštu. {t:collections.add} se ne nudi u zajedničkom sandučiću.
- Dan slanja može biti od 1. do 28. u mjesecu.
- {t:collections.recognise} traži uključenu umjetnu inteligenciju na instalaciji i vaš pristanak. Ako model nije dostupan ili je potrošen mjesečni iznos, uz zbirku stoji razlog, a poruke čekaju i čitaju se kad model ponovno bude dostupan. Primjeri razloga:
  - {t:error.ai_off}
  - {t:error.limit_reached}
- Poruka koju model ne može pročitati, primjerice jer je preduga, ostaje {t:collections.missed} i ne ulazi u tablicu. Dodajte je rukom ako je račun.
- {t:error.collecting_no_recipients}
- {t:error.collecting_invalid_senders}
- {t:error.collecting_invalid_since}
- {t:error.collecting_invalid_currency}
- {t:error.collecting_unrated}
- {t:error.mail_account_gone} Uz mjesec stoji ta poruka. Povežite račun ili odaberite drugi, pa pritisnite {t:collections.sendNow}.

## Povezano

- [Blokirani pošiljatelji i slike po domeni](help:mail/senders)
- [Pisanje poruke](help:mail/composing)
- [Računi e-pošte](help:mail/accounts)
- [Što agent može](help:agents/tools)
