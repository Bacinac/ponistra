# Glasovne naredbe

Mikrofon uz kutiju za pretragu pretvara izgovoreno u tekst, pa izvršava naredbu, otvara mjesto ili predlaže događaj, zadatak ili bilješku.

## Kako se koristi

### Snimanje

1. Pritisnite mikrofon uz kutiju za pretragu ({t:speech.say}) ili pritisnite {k:Alt-m}.
2. Prvi put otvara se pitanje {t:speech.consent.heading}. Pritisnite {t:speech.consent.agree} ako pristajete.
3. Dok se mikrofon uključuje, piše {t:speech.starting} a zatim {t:speech.listening} uz vrijeme snimanja. Govorite.
4. Pritisnite {t:speech.done}. Dok se zvuk pretvara u tekst, piše: {t:speech.writing}

### Što se događa s izgovorenim

1. Ako ste izgovorili točan naziv naredbe iz kutije za pretragu ili vaše poveznice, na primjer „Nova bilješka”, ona se odmah izvršava ili otvara.
2. Inače, kad je umjetna inteligencija uključena, piše {t:speech.reading} i Claude odlučuje što želite: otvoriti dio aplikacije ili kalendar na određeni dan, otvoriti poveznicu ili kontakt, nešto potražiti, započeti novi dokument ili poruku, dodati događaj ili zadatak, ili odgovoriti na pitanje o Ponistri člancima pomoći.
3. Poruka se otvara u obrascu za pisanje, s primateljima pronađenima među kontaktima.
4. Za događaj, zadatak i pitanje o Ponistri, i kad Claude ne prepozna naredbu, otvara se prozor {t:speech.heard}.

### Prozor s izgovorenim

1. U polju {t:speech.text} ispravite prepoznati tekst ako treba.
2. Ispod je {t:speech.proposed} s nazivom i vremenom događaja ili zadatka. Pritisnite {t:speech.toEvent} ili {t:speech.toTask} da biste ga provjerili i spremili.
3. {t:speech.toNote} sprema tekst kao novu bilješku.
4. Pod {t:speech.commands} su članci pomoći koji odgovaraju na pitanje i naredbe koje sadrže izgovorene riječi. Pritisnite jednu da biste je izvršili.

## Kako radi

Izgovoreno se šalje kao zvuk modelu za pretvaranje govora u tekst tvrtke OpenAI u SAD-u, ključem vaše instalacije. Zvuk se ne sprema u Ponistri. Tekst koji nije naziv naredbe, do 2000 znakova, čita Claude tvrtke Anthropic kad je umjetna inteligencija uključena za instalaciju; inače se odmah otvara prozor s izgovorenim.

Prijedlog događaja otvara obrazac događaja s nazivom, danom, vremenom i mjestom koje je Claude pročitao, a izgovoreni tekst postaje opis. Poruka odlazi s računa koji ste izgovorili, inače sa zadanog. Kad izgovoreno odgovara većem broju poveznica ili osoba, nude se sve, a vi birate. Na pitanje o Ponistri nude se članci pomoći koji sadrže njegove ključne riječi, a kad takvog nema, piše: {t:speech.noHelp}

Mikrofon uz polje za tekst, primjerice kod novog kruga na stranici [Projekti](help:agents/projects), istim pristankom samo upisuje izgovoreno u to polje i ništa ne izvršava.

Snimanje traje najviše 10 minuta i tada se samo zaustavlja. Pristanak se pamti uz vaš račun, a povlačite ga u [postavkama](/settings/ai), pod {t:consents.title}.

## Ograničenja

- Ako administrator nije uključio govor u tekst, mikrofon je onemogućen, a uz njega piše: {t:speech.off}
- Ako preglednik ne dopušta mikrofon, piše: {t:speech.microphone}
- Ako u snimci nema govora, piše: {t:speech.nothing}
- Ako osoba koju ste izgovorili nije među kontaktima, prozor to javlja i nudi ostale naredbe.
- Ako nemate račun pošte, piše: {t:speech.noAccount}
- Ako nemate kalendar u koji se može pisati, gumb za događaj je onemogućen: {t:speech.noCalendar}

## Povezano

- [Kutija za pretragu](help:start/search)
- [Bilješke](help:notes/overview)
- [Pisanje poruke](help:mail/composing)
