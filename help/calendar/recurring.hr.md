# Ponavljajući događaji

Događaj koji se ponavlja svaki dan, tjedan, mjesec ili godinu unosite jednom, a Ponistra zna i što s njim kad padne na neradni dan.

## Kako se koristi

### Ponavljanje

1. U događaju otvorite {t:calendar.field.repeat}. Mogućnosti se ravnaju prema danu početka: {t:calendar.repeat.daily}, {t:calendar.repeat.weekdays}, {t:calendar.repeat.weekly}, isti datum svakog mjeseca, isti dan u tjednu po redu u mjesecu (na primjer svaki drugi utorak u mjesecu), {t:calendar.repeat.yearly} ili {t:calendar.repeat.none}.
2. U polju {t:calendar.field.until} po želji upišite dan kad niz završava. Prazno polje znači da se događaj ponavlja bez kraja.
3. U polju {t:calendar.field.dayOff} birajte što se događa kad ponavljanje padne na vikend ili praznik: {t:calendar.dayOff.held}, {t:calendar.dayOff.skip}, ili se seli na {t:calendar.dayOff.before} odnosno {t:calendar.dayOff.after}.
4. Pritisnite {t:tree.save}.

### Promjena i brisanje

1. Promijenite jedno pojavljivanje i pritisnite {t:tree.save} ili {t:calendar.delete}.
2. U prozoru {t:calendar.editRecurring} ili {t:calendar.deleteRecurring}, pod {t:calendar.scope}, birajte {t:calendar.scope.this}, {t:calendar.scope.following} ili {t:calendar.scope.all}.
3. Potvrdite istim gumbom u tom prozoru.

## Kako radi

Ponavljanje po danu u mjesecu nudi se prema danu početka: za peti takav dan u mjesecu nudi se posljednji, a za posljednji koji je ujedno četvrti nude se oba. Neradni dani su vikend i praznici zemlje instalacije te dani koje administrator zatvori. Pojavljivanje koje bi se preselilo na dan na kojem niz već ima pojavljivanje izostaje.

{t:calendar.scope.this} mijenja samo to pojavljivanje, a ostatak niza ostaje kakav je bio. {t:calendar.scope.following} dijeli niz na dva: dosadašnji završava prije tog pojavljivanja, a novi počinje njime s vašim promjenama. {t:calendar.scope.all} mijenja cijeli niz; pomaknete li vrijeme, pomiče se svako pojavljivanje.

Kalendari na mobitelu i u drugim programima ne znaju za neradne dane Ponistre, pa im se šalje gdje pojedino pojavljivanje doista pada za sljedećih deset godina.

## Ograničenja

- Ponavljanje koje je stiglo iz drugog kalendara, a nije među ponuđenima, prikazuje se kao {t:calendar.repeat.custom} i čuva se takvo; mijenjati mu se može samo kraj.
- Pomak na radni dan traži radni dan u najviše 62 dana; ako ga nema, pojavljivanje izostaje.

## Povezano

- [Događaji](help:calendar/events)
- [Kalendar](help:calendar/overview)
