# Gosti

Osoba izvan instalacije ulazi u sastanak kao gost, preko poveznice, bez računa; netko iz sastanka je pušta unutra.

## Kako se koristi

### Ulazak kao gost

1. Otvorite poveznicu sastanka. Vidite naziv sastanka, sliku svoje kamere i tko je unutra.
2. Upišite {t:meeting.yourName} i pritisnite {t:meeting.join}.
3. Dok vas netko ne pusti, piše {t:meeting.waiting}
4. Ako imate račun u instalaciji, pritisnite {t:meeting.signIn}; {t:meeting.asGuest} vraća vas na ulazak kao gost.

### Puštanje gostiju

1. Kad gost čeka, u sastanku se pod {t:lobby.title} pojavljuje njegovo ime.
2. Pritisnite {t:lobby.admit} ili {t:lobby.refuse}.

## Kako radi

Gosta može pustiti svatko iz instalacije tko je u razgovoru sastanka, i prije nego što sam uđe u poziv, dok mu je sastanak otvoren. Osoba kojoj je poveznica stigla e-poštom iz Ponistre ima svoju poveznicu s već upisanim imenom i ulazi bez čekanja.

Gost u sastanku vidi i čuje sve, dijeli zaslon i piše u razgovor sastanka, a uz ime nosi oznaku {t:meeting.guest}. Ne može pozivati druge ni puštati goste. Osvježi li stranicu na istoj kartici, ne čeka ponovno na ulazu.

Gost ulazi istim putem kao članovi: kad instalacija ima vanjski relej sastanaka, slika i zvuk gostu idu kroz njega, pa ulazi i s mreže koja do instalacije ne dolazi izravno.

## Ograničenja

- Gost vidi samo taj sastanak i njegov razgovor, ništa drugo iz instalacije.
- Odbijeni gost ne ulazi u sastanak.
- Pred jednim sastankom može istodobno čekati najviše 20 gostiju koji su došli poveznicom sastanka u zadnjih 10 minuta. Sljedeći dobiva poruku: {t:error.door_full} Gostiju pozvanih e-poštom to ne ograničava.

## Povezano

- [Sastanci](help:meetings/overview)
- [Pozivanje u sastanak](help:meetings/inviting)
