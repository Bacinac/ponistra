# Međuspremnik

Izrezivanje, kopiranje i lijepljenje u tekstu, unutar Ponistre i između Ponistre i drugih programa.

## Kako se koristi

1. Označite tekst.
2. Desnom tipkom miša otvorite izbornik. U skupini {t:commandGroup.clipboard} su {t:command.cut} ({k:Mod-x}), {t:command.copy} ({k:Mod-c}), {t:command.paste} ({k:Mod-v}) i {t:command.pasteText} ({k:Shift-Mod-v}).
3. {t:command.pasteText} lijepi samo tekst, bez oblikovanja.
4. {t:command.blockLink} kopira adresu odlomka u kojem stojite.

## Kako radi

Kopirani sadržaj nosi i oblikovanje i čisti tekst, pa ga drugi programi lijepe kako im odgovara. Tablice se prenose kao retci ćelija, boje kakve su na papiru, popisi kao popisi, a bilješke onako kako ih zapisuje Word: broj u tekstu, a bilješka na kraju kopiranog. U čistom tekstu bilješka je broj u uglatoj zagradi, a njezin tekst popisan je na kraju.

Fusnote i završne bilješke zalijepljene iz Worda ili LibreOfficea ponovno postaju bilješke na svom mjestu u tekstu.

## Ograničenja

- Naredbe iz izbornika traže da preglednik dopusti pristup međuspremniku. Kad ga ne dopusti, javlja se {t:command.failed} s preporukom da koristite tipkovničke prečace, koji rade i tada.
- {t:command.cut}, {t:command.paste} i {t:command.pasteText} nisu dostupni kad dokument samo čitate.

## Povezano

- [Poveznice](help:text/links)
- [Bilješke](help:text/notes)
- [Prečaci](help:text/shortcuts)
