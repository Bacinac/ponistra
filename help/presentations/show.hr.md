# Izlaganje

Izlaganje prikazuje slajdove dokumenta preko cijelog zaslona, a izlagački prikaz u drugom prozoru pokazuje bilješke, sljedeći slajd i vrijeme.

## Kako se koristi

### Pokretanje

1. Pritisnite naslov dokumenta u putanji i u izborniku odaberite {t:command.presentStart} ili {t:command.present}. Uz pravo uređivanja isti gumbi su i na traci alata u prikazu {t:view.slides}.
2. Klik ili {k:ArrowRight} vodi na sljedeći slajd, a {k:ArrowLeft} na prethodni. {k:Home} i {k:End} vode na prvi i posljednji slajd.
3. Upišite broj slajda i pritisnite {k:Enter} za skok na taj slajd.
4. {k:Escape} ili {t:show.end} završava izlaganje.

### Izlagački prikaz

1. Pomaknite miš: na dnu zaslona pojavljuju se {t:show.previous}, {t:show.next}, {t:show.presenter} i {t:show.end}, a kad izlaganje ne zauzima cijeli zaslon i {t:show.fullScreen}.
2. Pritisnite {t:show.presenter}. Otvara se zaseban prozor, koji možete premjestiti na drugi zaslon.
3. U njemu su {t:show.current}, sljedeći slajd, {t:command.speakerNotes}, {t:show.elapsed} i {t:show.clock}.
4. {t:show.pause}, {t:show.resume} i {t:show.restart} upravljaju mjerenjem vremena. {t:show.previous} i {t:show.next} pomiču izlaganje.

## Kako radi

Izlaganje prolazi kroz slajdove svih kartica redom i preskače skrivene slajdove, osim kad do skrivenog slajda dođete upisom njegova broja. Iza posljednjeg slajda je završni zaslon; sljedeći klik završava izlaganje. Kad izađete iz cijelog zaslona, izlaganje završava.

Izlagački prikaz i izlaganje rade u istom pregledniku i prate jedno drugo: pomak u jednom prozoru pomiče i drugi. U izlagačkom prikazu piše {t:show.slide} s brojem trenutnog slajda i ukupnim brojem slajdova, a iza posljednjeg {t:show.over}.

## Ograničenja

- Preglednik mora dopustiti skočne prozore za Ponistru da bi se otvorio izlagački prikaz.
- Izlagački prikaz ne može se otvoriti na drugom uređaju.

## Povezano

- [Slajdovi](help:presentations/slides)
- [Ispis](help:text/print)
