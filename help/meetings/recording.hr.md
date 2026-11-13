# Snimanje sastanka

Sastanak se snima u mapu u vašim dokumentima, svaki sudionik kao zasebna datoteka, a iz izgovorenog nastaje zapisnik sa zadacima.

## Kako se koristi

### Snimanje

1. U sastanku pritisnite {t:recording.start}. Svi u sastanku, i gosti, uz naziv sastanka vide {t:recording.on}.
2. Za kraj pritisnite {t:recording.stop}. Snimanje zaustavlja svatko iz instalacije tko je u pozivu.
3. Kad svi izađu iz sastanka, snimanje završava samo nakon jedne minute.

### Pristanak na prijepis

1. Kad snimanje počne, sudionik koji još nije dao pristanak vidi pitanje {t:recording.ask}
2. Pritisnite {t:recording.agree} ili {t:recording.refuse}. Odgovor vrijedi za to snimanje.

### Snimke sastanka

1. Otvorite sastanak. Ispod sudionika, prije ulaska ili nakon izlaska, stoji {t:recording.list} s vremenom početka svake snimke.
2. {t:recording.folder} otvara mapu snimke, a {t:recording.minutes} zapisnik.
3. {t:recording.play} pušta sve snimke sudionika zajedno, svaku od trenutka kad se uključila. Klizač pomiče cijelu snimku odjednom.
4. Dok se snimka sprema, uz vrijeme piše {t:recording.saving}. Ako spremanje ne uspije, uz vrijeme piše razlog, a osoba koja je pokrenula snimanje pritiskom na {t:recording.again} pokreće ga ponovno.

## Kako radi

Snimač ulazi u sastanak kao nevidljivi sudionik i zapisuje zvuk i sliku svakog sudionika onako kako su poslani, bez ponovnog kodiranja: mikrofon, kameru, zaslon i zvuk zaslona, svaki u svoju WebM datoteku. Uključi li netko kameru dvaput, nastaju dvije datoteke.

Nakon kraja posao u pozadini sprema snimku u novu mapu na vrhu dokumenata osobe koja je pokrenula snimanje, s nazivom sastanka i vremenom početka. Datoteke nose ime sudionika i izvor, na primjer „Ana Horvat – kamera”. Kolege iz instalacije koji su bili u sastanku mapu mogu čitati.

Zapisnik nastaje kad je u instalaciji uključeno pretvaranje govora u tekst. Prepisuje se samo govor onih koji su pristali: kolege koji su pristanak dali u [Pristancima](help:ai/consents), osim ako su u sastanku odgovorili {t:recording.refuse}, i sudionici, gosti također, koji su odgovorili {t:recording.agree}. Svaki iskaz prepisuje se zasebno, pa prijepis zna tko je što rekao i kada. Kad je uključen i model, on iz prijepisa piše sažetak, odluke i zadatke. Svaki zadatak dodjeljuje osobi koju prijepis za njega imenuje, a kad je ne imenuje, osobi koja je pokrenula snimanje, s rokom kad je rečen. Zapisnik je dokument u mapi snimke. U njemu su zadaci kao popis za označavanje, prisutni i cijeli prijepis, a zadaci su i u [Zadacima](help:tasks/overview) s poveznicom na zapisnik. Bez modela zapisnik sadrži samo prisutne i prijepis.

Snimač čuva datoteke dok se ne spreme u stablo i dok zapisnik ne bude napisan, pa ponovno spremanje nastavlja ondje gdje je zapelo.

## Ograničenja

- Snima se slika poslana u VP8 i zvuk u Opusu, kako ih šalju preglednici. Ostalo se preskače.
- Gost ne pokreće ni ne zaustavlja snimanje i ne vidi snimke.
- Sastanak istodobno ima jedno snimanje. Pokrene li ga netko drugi u isto vrijeme: {t:error.already_recording}
- Snimanje pokreće i zaustavlja samo netko tko je u pozivu. Ostali dobivaju poruku {t:error.not_in_call}
- Kad snimač ili poslužitelj sastanaka ne odgovara, piše {t:error.recording_unavailable} Obratite se administratoru.
- {t:error.not_started} Takva snimka nema ništa za spremanje.
- {t:error.recorder_unavailable} Pokušajte ponovno s {t:recording.again} kad snimač ponovno radi.
- {t:error.unsaved} Pokušajte ponovno s {t:recording.again}.
- {t:error.no_owner}
- Kad pretvaranje govora u tekst ne uspije, uz snimku piše razlog, na primjer da je ključ odbijen. Mapa je tada već spremljena, a {t:recording.again} piše samo zapisnik.

## Povezano

- [Sastanci](help:meetings/overview)
- [Pristanci](help:ai/consents)
- [Zadaci](help:tasks/overview)
