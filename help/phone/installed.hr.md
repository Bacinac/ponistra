# Instalirana aplikacija

Ponistru instalirate iz preglednika na računalo ili telefon, pa se otvara u vlastitom prozoru, s ikonom koja broji nepročitano.

## Kako se koristi

1. Instalirajte Ponistru iz izbornika preglednika ili iz postavki obavijesti, kako opisuju [obavijesti](help:account/notifications).
2. Otvorite je ikonom na računalu ili telefonu.
3. Dugi pritisak ili desni klik na ikonu nudi novu bilješku i govor naredbe ili bilješke.

## Kako radi

Ikona aplikacije pokazuje broj nepročitanih poruka u ulaznim sandučićima vaših računa e-pošte i nepročitanih poruka u razgovorima (u kanalima samo spominjanja i odgovora u nitima koje pratite); dok je aplikacija zatvorena, broj se mijenja iz obavijesti koje stižu. Naslov prozora je naziv otvorene stranice, bez imena Ponistre, koje preglednik sam piše na početku.

Aplikacija se drži jednog glavnog prozora: ponovno pokretanje dovodi otvoreni prozor naprijed, a poveznica otvorena izvana otvara se u njemu. Sastanak, prezentacija i datoteka u zasebnom prozoru predaju takvo otvaranje glavnom prozoru; ako on nije otvoren, pokazuju poruku i gumb {t:launch.open}.

Instalirana aplikacija može otvarati datoteke s računala, preko „Otvori pomoću”: dokumente koje Ponistra uvozi i PDF. Svaka datoteka otvara se u vlastitom prozoru, sama preko cijelog prozora, s imenom, radnjama i {t:device.close} u stupcu iznad kartica i naslova; glavni prozor ostaje gdje je bio. Dok se učitava, prozor pokazuje {t:launch.receiving} Ako se u međuvremenu zatvori glavni prozor koji ju je primio, prozor javlja {t:launch.lost} Preglednik koji ne dopušta da se prozor otvori bez vašeg klika ostavlja datoteku u glavnom prozoru, u okviru {t:launch.held} dolje desno, gdje je gumb {t:launch.window} otvara; dopustite li u pregledniku skočne prozore za Ponistru, otvarat će se sama.

Datoteka postaje dokument bez mape: nije među Mojim dokumentima, a nalazite je u nedavnim dokumentima i tražilici, gdje joj umjesto mape piše {t:tree.unplaced}. Sadržaj se sprema čim ga promijenite, kao u svakom dokumentu. {t:tree.saveInto} u zaglavlju otvara {t:tree.saveTitle}, gdje mapu birate i potvrđujete s {t:tree.saveHere}; tek tada dokument dobiva mjesto. Dokument bez mape koji 30 dana nitko ne otvori ni ne promijeni odlazi u smeće, odakle ga možete vratiti.

Dok niste prijavljeni, PDF se otvara sam preko cijelog prozora, bez ostatka aplikacije, sa stranicom, pretragom i naslovima datoteke u stupcu sa strane, i ne šalje se poslužitelju; više datoteka otvorenih odjednom stoji u traci {t:device.files} na vrhu, a {t:device.close} vodi na prijavu. Ostale datoteke čekaju prijavu. Poveznicu e-pošte (`mailto:`) koja stigne u Ponistru aplikacija otvara kao novu poruku sa zadanog računa, s primateljima, predmetom i tekstom iz poveznice.

Sadržaj iz drugih aplikacija dijelite u Ponistru, kako opisuje [dijeljenje s Ponistrom](help:phone/share).

## Ograničenja

- Broj na ikoni i otvaranje datoteka ovise o tome podržavaju li ih preglednik i sustav.
- Izbor na ikoni dobiva jezik vašeg računa tek kad preglednik osvježi instaliranu aplikaciju, što može potrajati nekoliko dana.
- Na Androidu Ponistra ima i [vlastitu aplikaciju](help:phone/android), koja uz to drži kontakte i kalendare u telefonu.

## Povezano

- [Obavijesti](help:account/notifications)
- [Dijeljenje s Ponistrom](help:phone/share)
- [Android aplikacija](help:phone/android)
