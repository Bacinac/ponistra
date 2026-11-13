# Poveznice

Poveznica u tekstu vodi na web-stranicu, adresu e-pošte, telefonski broj, drugi dokument Ponistre ili točno mjesto u dokumentu.

## Kako se koristi

### Nova poveznica

1. Odaberite tekst koji postaje poveznica ili samo stanite na mjesto u tekstu.
2. Pritisnite {t:command.link} ({k:Mod-k}) u izborniku {t:editor.insert}.
3. Upišite {t:link.text} i {t:link.href}, ili pod {t:link.find} upišite naziv dokumenta i odaberite ga.
4. Pritisnite {t:tree.save}.

### Postojeća poveznica

1. Stanite u poveznicu. Ispod nje pojavljuje se adresa s gumbima.
2. Pritisnite adresu ili {t:link.open} da biste je otvorili, {t:link.edit} za izmjenu ili {t:link.remove} da tekst ostane bez poveznice.

### Poveznica na mjesto u dokumentu

1. Stanite u odlomak ili odaberite tekst.
2. Desnom tipkom miša odaberite {t:command.blockLink}.
3. Zalijepite poveznicu u poruku, drugi dokument ili razgovor.

## Kako radi

Poveznica na dokument ili stranicu Ponistre otvara se u istoj kartici preglednika, a svaka druga u novoj. Poveznica na mjesto otvara dokument na toj kartici i tom odlomku, a ako je bio odabran tekst, vodi upravo na njega.

Kad nije upisan tekst, poveznica prikazuje adresu, a kad je odabran dokument iz pretrage, njegov naziv.

## Ograničenja

- Adresa mora početi s `http://`, `https://`, `mailto:` ili `tel:`, ili voditi na dokument Ponistre. Inače se ne sprema, a dijalog to javlja.
- Poveznicu na mjesto otvara samo onaj tko ima pristup dokumentu.

## Povezano

- [Umetanje](help:text/insert)
- [Međuspremnik](help:text/clipboard)
- [Dijeljenje](help:documents/sharing)
