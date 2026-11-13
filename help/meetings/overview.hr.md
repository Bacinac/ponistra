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
- {t:meeting.share} dijeli vaš zaslon, prozor ili karticu sa svima; {t:meeting.stopSharing} prekida dijeljenje.
- {t:chat.messages} otvara razgovor sastanka uz sliku; broj na gumbu kaže koliko poruka niste pročitali.
- {t:meeting.nextScreen} seli prozor sastanka na drugi zaslon, kad ga računalo ima.
- {t:recording.start} snima sastanak, a iz izgovorenog nastaje zapisnik ([Snimanje sastanka](help:meetings/recording)).
- Broj uz naslov kaže koliko je osoba unutra ({t:meeting.people}).
- {t:meeting.leave} izlazi iz sastanka; nakon toga {t:meeting.rejoin} vraća vas unutra, a {t:meeting.back} vodi natrag.

## Kako radi

Sastanak u Ponistri otvara se u zasebnom prozoru uz vaš rad. Ako preglednik ne dopusti zaseban prozor, sastanak se otvara na istoj kartici i iznad njega stoji upozorenje da dopustite skočne prozore za tu stranicu.

Novi sastanak nastaje tek kad u njega uđete ili nekoga pozovete; zatvorite li ga prije toga, ne ostaje ništa. Svaki sastanak ima svoj razgovor, koji ostaje i nakon poziva. Dok dijelite zaslon, on se ne prikazuje vama, da se ne bi umnažao sam u sebi; piše {t:meeting.presenting}

Gosti, i oni pozvani izvana, nose oznaku {t:meeting.guest}, a vi {t:meeting.you}. Isključen mikrofon označen je uz ime ({t:meeting.muted}). Ako se veza prekine, piše {t:meeting.reconnecting} i Ponistra se sama spaja ponovno; ako ne uspije, piše {t:meeting.dropped}

## Ograničenja

- Ako preglednik ne dopusti ni kameru ni mikrofon, ući se može tek kad ih dopustite u postavkama stranice.
- Bez mreže se u sastanak ne ulazi: {t:meeting.join} i {t:meeting.rejoin} tada su onemogućeni ({t:offline.needed}). Sastanak u kojem već jeste ne prekida se zbog toga.
- Ako preglednik ne pusti zvuk sam od sebe, pritisnite {t:meeting.playAudio}.
- Kad instalacija ima vanjski relej sastanaka, a on trenutno nije dostupan, ulazak se odbija porukom {t:error.relay_unreachable} Javite se administratoru instalacije.
- Premještanje na drugi zaslon traži dopuštenje za upravljanje prozorima u postavkama stranice.

## Povezano

- [Slika kamere i zvuk u sastanku](help:meetings/camera)
- [Pozivanje u sastanak](help:meetings/inviting)
- [Gosti](help:meetings/guests)
- [Snimanje sastanka](help:meetings/recording)
- [Događaji](help:calendar/events)
- [Razgovori](help:chat/overview)
