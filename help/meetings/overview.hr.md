# Sastanci

Sastanak je video poziv unutar Ponistre: kolege ulaze poveznicom, a osobe izvan instalacije kao gosti.

## Kako se koristi

### Ulazak u sastanak

1. Sastanak otvarate gumbom {t:meeting.join} u događaju, na stranici Danas ili u razgovoru, a novi sastanak gumbom {t:meeting.now} u razgovorima.
2. Prije ulaska vidite sliku svoje kamere i tko je već unutra ({t:meeting.present}), ili {t:meeting.nobody}
3. Prekidačima {t:meeting.micOff} i {t:meeting.cameraOff} uđite s isključenim mikrofonom ili kamerom; {t:meeting.devices} bira {t:meeting.camera}, {t:meeting.microphone} i {t:meeting.speaker}, koje uređaj pamti za sljedeći sastanak, te pozadinu i obradu zvuka ([Slika kamere i zvuk u sastanku](help:meetings/camera)).
4. Pritisnite {t:meeting.join}, ili {t:tree.cancel} za odustajanje.

### U sastanku

- {t:meeting.micOff} i {t:meeting.micOn}, {t:meeting.cameraOff} i {t:meeting.cameraOn} isključuju i uključuju mikrofon i kameru.
- {t:meeting.share} otvara izbornik: {t:meeting.shareTab}, {t:meeting.shareWindow} ili {t:meeting.shareScreen}, što preglednik zatim nudi prvo; dok dijelite, na tom je mjestu {t:meeting.stopSharing}. Ispod su adrese sastanka koje namjeravate dijeliti: klik otvara adresu u novoj kartici, {t:meeting.openTabs} otvara sve odjednom.
- {t:meeting.share} → {t:meeting.shareBoard} nudi vaše ploče po skupinama; odabrana ploča svima u sastanku, i gostima, prikazuje se na pozornici, a {t:meeting.stopSharing} je skida. Bez ijedne ploče izbornik kaže {t:meeting.noBoards}
- {t:meeting.editTabs} otvara {t:meeting.tabsTitle}, zajedničke svima u sastanku: polje adrese nudi kartice vaših prijašnjih sastanaka, omiljeno, poveznice i nedavne dokumente, a tipkanjem se popis sužava; odabir ili {t:meeting.addTab} dodaje adresu, a {t:meeting.removeTab} je briše s popisa. Ploča s popisa ide na pozornicu kao {t:meeting.shareBoard}, a svaka druga adresa otvara se u novoj kartici koju zatim dijelite. Preglednik ne daje Ponistri popis vaših otvorenih kartica; njih nudi tek njegov prozor za dijeljenje.
- {t:meeting.float} otvara malen prozor iznad svih ostalih s crvenim okvirom, slikom onoga što dijelite i gumbom {t:meeting.stopSharing}.
- {t:chat.messages} otvara razgovor sastanka uz sliku; broj na gumbu kaže koliko poruka niste pročitali.
- {t:meeting.nextScreen} seli prozor sastanka na drugi zaslon, kad ga računalo ima.
- {t:recording.start} snima sastanak, a iz izgovorenog nastaje zapisnik ([Snimanje sastanka](help:meetings/recording)).
- Broj uz naslov kaže koliko je osoba unutra ({t:meeting.people}).
- {t:meeting.leave} izlazi iz sastanka; nakon toga {t:meeting.rejoin} vraća vas unutra, a {t:meeting.back} vodi natrag.

## Kako radi

Sastanak u Ponistri otvara se u zasebnom prozoru uz vaš rad. Ako preglednik ne dopusti zaseban prozor, sastanak se otvara na istoj kartici i iznad njega stoji upozorenje da dopustite skočne prozore za tu stranicu.

Novi sastanak nastaje tek kad u njega uđete ili nekoga pozovete; zatvorite li ga prije toga, ne ostaje ništa. Svaki sastanak ima svoj razgovor, koji ostaje i nakon poziva. Dok dijelite, kamere ostaju na cijeloj pozornici, a ispod njih je umanjena slika onoga što dijelite ({t:meeting.sharingTab}, {t:meeting.sharingWindow} ili {t:meeting.sharingScreen}) s gumbom {t:meeting.stopSharing}. Kad dijeli netko drugi, njegovo dijeljenje zauzima pozornicu, a kamere su uz njega. Kartica sastanka ne nudi se za dijeljenje. Dok dijelite karticu, preglednik na njoj nudi da umjesto nje dijelite karticu na kojoj ste, pa se kartice izmjenjuju jednim klikom, bez prekida dijeljenja. Ploču koju dijelite svatko u sastanku vidi u svom pregledniku, oštru i živu: kad se njezini podaci ili stranica promijene, mijenja se svima. Gledatelji je mogu samo čitati, i to samo dok ste vi i oni u pozivu; kad izađete iz poziva, ploča silazi s pozornice. Dok je ploča na pozornici, ne dijeli se ni zaslon ni druga ploča.

Gosti, i oni pozvani izvana, nose oznaku {t:meeting.guest}, a vi {t:meeting.you}. Isključen mikrofon označen je uz ime ({t:meeting.muted}). Ako se veza prekine, piše {t:meeting.reconnecting} i Ponistra se sama spaja ponovno; ako ne uspije, piše {t:meeting.dropped}

## Ograničenja

- Ako preglednik ne dopusti ni kameru ni mikrofon, ući se može tek kad ih dopustite u postavkama stranice.
- Bez mreže se u sastanak ne ulazi: {t:meeting.join} i {t:meeting.rejoin} tada su onemogućeni ({t:offline.needed}). Sastanak u kojem već jeste ne prekida se zbog toga.
- Ako preglednik ne pusti zvuk sam od sebe, pritisnite {t:meeting.playAudio}.
- Premještanje na drugi zaslon traži dopuštenje za upravljanje prozorima u postavkama stranice.

## Povezano

- [Slika kamere i zvuk u sastanku](help:meetings/camera)
- [Pozivanje u sastanak](help:meetings/inviting)
- [Gosti](help:meetings/guests)
- [Snimanje sastanka](help:meetings/recording)
- [Događaji](help:calendar/events)
- [Razgovori](help:chat/overview)
