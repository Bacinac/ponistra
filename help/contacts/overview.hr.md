# Kontakti

Adresar drži osobe s kojima se dopisujete: adrese e-pošte, brojeve telefona, adrese i rođendane, na jednom mjestu za sve vaše račune i uređaje.

## Kako se koristi

### Traženje i otvaranje

1. Otvorite [kontakte](/contacts) na traci s lijeve strane.
2. U polje {t:contacts.search} upišite početak imena, tvrtke, radnog mjesta, adrese ili broja.
3. Kliknite kontakt. Na širokom zaslonu otvara se uz popis, a dok ništa nije odabrano piše {t:contacts.choose}

### Kontakt

- Adresa e-pošte otvara novu poruku tom kontaktu, broj telefona poziva ga s uređaja koji to može, a web adresa otvara se u novoj kartici.
- Zvjezdica {t:contacts.star} ili {t:contacts.unstar} uz ime dodaje kontakt u omiljene ili ga iz njih uklanja; omiljeni nose oznaku {t:contacts.starred}.
- {t:contacts.edit} otvara kontakt za uređivanje, kako opisuje [uređivanje kontakta](help:contacts/editing).
- U izborniku uz {t:contacts.edit} su {t:contacts.addPhoto} ({t:contacts.changePhoto} kad fotografija postoji), {t:contacts.removePhoto} i {t:contacts.delete}, koje traži potvrdu ({t:contacts.deleteTitle})

### Više kontakata odjednom

1. Dugo pritisnite kontakt u popisu; nakon toga dodir ili klik dodaje kontakt u odabir ili ga iz njega uklanja. Traka odabira pokazuje {t:explorer.selected} s brojem odabranih. Desni klik na kontakt nudi iste radnje, a {k:Delete} briše odabrane uz potvrdu.
2. Na traci odabira {t:contacts.write} otvara jednu poruku svim odabranima koji imaju adresu e-pošte.
3. {t:contacts.star} i {t:contacts.unstar} mijenjaju omiljene za sve odabrane.
4. {t:contacts.deleteMany} traži potvrdu ({t:contacts.deleteManyTitle}) pa briše odabrane.

Ispod popisa, pod {t:mail.mailboxes}, otvarate kontakte [zajedničkog sandučića](help:mail/mailboxes) koji je podijeljen s vama, a {t:contacts.mailboxOwn} vraća vaše.

## Kako radi

Kontakti dolaze sami iz povezanih računa pošte (Google, Microsoft, ActiveSync) i iz imenika organizacije, a možete ih dodavati i sami. Svaku osobu iz računa Ponistra preuzima jednom i spaja je s kontaktom koji već ima istu adresu, isti broj ili isto ime; nakon toga kontakt je vaš i mijenjate ga ovdje. Uz kontakt, pod {t:contacts.sources}, piše odakle je došao i kada, a ispod toga {t:contacts.changed} s datumom zadnje promjene.

Broj se pronalazi i kad ga upišete bez pozivnog broja zemlje, pa 091 pronalazi +385 91 234 5678. Kontakt bez imena u popisu se zove {t:contacts.unnamed}. Kad ništa ne odgovara traženju, piše: {t:contacts.noMatch}

Adresar je isti na webu, u aplikaciji i na mobitelu koji ga čita preko CardDAV-a; {t:contacts.phones} u izborniku stranice otvara lozinke za aplikacije na mobitelu, kako opisuje [Android aplikacija](help:phone/android). Ako se račun ne može dohvatiti, iznad popisa piše račun i razlog.

## Ograničenja

- Izbrisani kontakt nestaje iz adresara i s mobitela, a račun iz kojeg je došao više ga ne donosi.
- Preuzimanje iz računa ide u jednom smjeru: promjena u Ponistri ne vraća se računu iz kojeg je kontakt došao.

## Povezano

- [Uređivanje kontakta](help:contacts/editing)
- [Imenik organizacije](help:contacts/directory)
- [Pisanje poruke](help:mail/composing)
- [Zajednički sandučići](help:mail/mailboxes)
