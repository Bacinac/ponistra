# Prijevod

Poruke i PDF datoteke na jeziku koji ne čitate Claude prevodi na jezik sučelja, a odgovor na takvu poruku na jezik poruke.

## Kako se koristi

### Jezici koje čitate

1. Otvorite {t:settings.title} i odaberite {t:translation.title}.
2. Pod {t:translation.reads} dodajte jezik iz popisa {t:translation.add}
3. Jezik uklanjate gumbom {t:translation.remove} uz njegov naziv.

### Poruka na drugom jeziku

1. Iznad poruke na jeziku koji ne čitate stoji traka s jezikom poruke.
2. Pritisnite {t:translation.translate}. Dok traje, piše: {t:translation.translating}
3. Pritisnite {t:translation.original} za povratak na izvornik.
4. Kad Ponistra ne prepozna jezik poruke, {t:translation.translate} je u izborniku poruke.

### Odgovor na drugom jeziku

1. Napišite odgovor na svojem jeziku.
2. Pritisnite {t:translation.reply}.
3. Uz vaš tekst pojavljuje se prijevod, koji možete ispraviti prije slanja.
4. Pritisnite {t:translation.edit} za povratak na vlastiti tekst.

### PDF na drugom jeziku

1. U izborniku otvorene PDF datoteke odaberite {t:action.fileTranslate.ask}
2. U dijalogu {t:translation.file} pritisnite {t:translation.translate}.

## Kako radi

Ponistra sama prepoznaje jezik poruke ili PDF-a i nudi prijevod samo kad taj jezik nije među jezicima koje čitate. Dok jezike ne odaberete, čitate jezik sučelja. Prijevod poruke Claude piše odlomak po odlomak, pa izgled, slike i poveznice ostaju. Prevedena poruka čuva se, pa se kod sljedećeg otvaranja ne prevodi ponovno.

Kod prvog prijevoda poruke otvara se dijalog {t:ai.consent.heading} s izborom {t:ai.consent.once} ili {t:translation.consent.always}. Uz drugi izbor poruke na jeziku koji ne čitate prevode se čim ih otvorite, a odgovori bez pitanja; to mijenjate u postavkama, pod {t:consents.title}.

Kad pošaljete prevedeni odgovor, odlazi prijevod, a poslana poruka čuva i ono što ste napisali na svojem jeziku. PDF se prevodi stranicu po stranicu u novi dokument pokraj datoteke; na traci radnje piše {t:action.fileTranslate}, a {t:run.missed} navodi stranice koje nisu prevedene.

## Ograničenja

- Prijevod se nudi samo dok je umjetna inteligencija uključena za instalaciju.
- Uvijek mora ostati barem jedan jezik koji čitate.
- PDF se prevodi samo na jezik sučelja, a pritisak na {t:translation.translate} u dijalogu ujedno je pristanak za to jedno slanje.

## Povezano

- [Pristanci](help:ai/consents)
- [Čitanje poruke](help:mail/reading)
- [Pisanje poruke](help:mail/composing)
