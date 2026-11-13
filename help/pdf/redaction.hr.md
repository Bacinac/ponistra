# Zacrnjivanje

Zacrnjivanje izrađuje kopiju PDF-a iz koje je trajno uklonjeno ono što ste označili, primjerice osobni podaci prije slanja dokumenta.

## Kako se koristi

### Označavanje

1. Pritisnite {t:pdf.redact} na traci. Pojavljuje se traka alata za zacrnjivanje.
2. Povucite pravokutnik preko onoga što treba zacrniti. Oznaka se prikazuje šrafirano.
3. Tekst možete označiti i tako da ga odaberete i pritisnete {t:pdf.redact} uz odabir.
4. Za sve pojave nekog teksta otvorite pretragu, upišite tekst i pritisnite {t:pdf.redact.found}. Obavijest {t:pdf.redact.marked} navodi broj pogodaka.
5. Pritisnite oznaku pa {t:pdf.remove} ili {k:Delete} da biste je uklonili.

### Zacrnjena kopija

1. Na traci alata za zacrnjivanje pritisnite {t:pdf.redact.save}
2. U dijalogu {t:pdf.redact.save.heading} potvrdite ili promijenite naziv. Predloženi naziv je naziv datoteke s dodatkom „(zacrnjeno)”.
3. Kopija se sprema uz izvornik i otvara kad je gotova.

## Kako radi

Iz kopije se uklanjaju tekst, slike i crteži ispod oznaka, a na njihovo mjesto crta se crni pravokutnik. Uklanjaju se i poveznice, bilješke i polja obrasca koje oznake dodiruju, a iz cijele kopije metapodaci, privici, skripte, sličice stranica i ranije inačice datoteke. Prije spremanja kopija se ponovo čita: ostane li ispod oznake ijedan znak, kopija se ne sprema.

Izvorna datoteka i oznake ostaju kakvi jesu, pa kopiju možete izraditi ponovo. Bilješke i vrijednosti obrasca koje oznake ne dodiruju prenose se u kopiju.

## Ograničenja

- Zacrnjivanje se nudi samo onome tko smije uređivati datoteku.
- Datoteka zaštićena lozinkom i datoteka koja zabranjuje izmjene sadržaja ne mogu se zacrniti.
- Digitalni potpisi datoteke ne prenose se u kopiju.
- Kad u mapi datoteke ne smijete dodavati, kopija se sprema među vaše dokumente.

## Povezano

- [Bilješke i komentari u PDF-u](help:pdf/notes)
- [PDF datoteke](help:pdf/viewer)
