# Slika kamere i zvuk u sastanku

Pozadina iza vas, praćenje lica, popravak slabog osvjetljenja i obrada zvuka mikrofona biraju se uz uređaje, prije ulaska u sastanak i u njemu.

## Kako se koristi

### Pozadina

1. Prije ulaska ili u sastanku pritisnite {t:meeting.devices}, pa {t:meeting.background}.
2. Odaberite {t:meeting.background.none}, {t:meeting.background.soft}, {t:meeting.background.strong} ili jednu od ugrađenih slika: {t:meeting.background.petrol}, {t:meeting.background.sage}, {t:meeting.background.paper} i {t:meeting.background.evening}.
3. Za svoju sliku pritisnite {t:meeting.backdropUpload} i odaberite fotografiju. Ona odmah postaje pozadina, a na popisu se pojavljuje kao {t:meeting.background.own}.
4. {t:meeting.backdropRemove} briše vašu sliku, a pozadina se vraća na {t:meeting.background.none}.

### Lice i osvjetljenje

1. Pritisnite {t:meeting.devices}.
2. {t:meeting.framing} uključuje i isključuje kadriranje koje prati vaše lice.
3. {t:meeting.light} uključuje i isključuje posvjetljivanje slike kad je prostorija tamna.

### Zvuk

1. Pritisnite {t:meeting.devices}, pa {t:meeting.sound}.
2. {t:meeting.noise}, {t:meeting.echo} i {t:meeting.gain} uključuju se i isključuju svaki zasebno. Sva tri su zadano uključena.

## Kako radi

Sliku i zvuk obrađuje vaš preglednik, na vašem uređaju, prije nego što ih pošalje. Drugi sudionici i snimka sastanka dobivaju već obrađenu sliku. Model koji odvaja osobu od pozadine i model koji traži lice dolaze s vaše instalacije Ponistre, ne s vanjskih poslužitelja.

Izbor obrade pamti vaš račun, pa vrijedi na svakom uređaju na kojem se prijavite. Kameru, mikrofon i zvučnik koje ste odabrali pamti svaki uređaj za sebe, jer drugi uređaj ima druge. Gost nema račun, pa njegov izbor pamti preglednik u kojem je ušao.

Vlastitu sliku preglednik prije slanja smanji na najviše 1920 × 1080 točaka i spremi uz vaš račun. Vidite je samo vi, a drugi je vide samo iza vas u pozivu. Ulazi u izvoz vaših podataka.

{t:meeting.framing} nekoliko puta u sekundi traži lica na slici i polako pomiče izrez tako da lice stoji u gornjem dijelu slike. Kad je na slici više osoba, izrez obuhvaća sve. Kad lica nema dulje od 3 sekunde, slika se vraća na cijeli kadar. {t:meeting.light} dvaput u sekundi mjeri svjetlinu slike i tamnu sliku posvijetli najviše dvostruko. Svijetla slika ostaje kakva jest.

Zvuk obrađuje sam preglednik. Promjena prekidača odmah vrijedi za mikrofon u sastanku. Isključen mikrofon ostaje isključen.

Ako uređaj ne stiže obraditi sliku u vremenu između dvije slike kamere, Ponistra najprije isključi pozadinu i javi {t:meeting.strainedBackground} Ako ni to nije dovoljno, isključi svu obradu i javi {t:meeting.strainedAll} Slika tada ide bez obrade, a vaš izbor ostaje zapamćen.

## Ograničenja

- Gost ne može učitati vlastitu sliku.
- Vlastita slika može biti PNG, JPEG, WebP, GIF ili AVIF. Datoteka koja nije slika se odbija ({t:error.not_a_photo}).
- Preglednik koji ne može obrađivati sliku kamere nudi pozadinu, lice i osvjetljenje onemogućene, s napomenom {t:meeting.unshapeable} Zvuk se i tada bira.
- Kad obrada ne uspije, ispod slike piše {t:meeting.shapingFailed} i razlog. {t:meeting.retry} pokušava ponovno, kao i nakon isključivanja zbog opterećenja.
- Obrada slike troši procesor i grafičku karticu. Na slabijem uređaju odaberite {t:meeting.background.soft} umjesto slike ili isključite {t:meeting.framing}.

## Povezano

- [Sastanci](help:meetings/overview)
- [Snimanje sastanka](help:meetings/recording)
- [Gosti](help:meetings/guests)
