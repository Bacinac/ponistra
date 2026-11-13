# Bilješke

Fusnote i završne bilješke dopunjuju tekst bez prekidanja: u tekstu stoji broj, a bilješka je popisana ispod teksta kartice.

## Kako se koristi

### Nova bilješka

1. Stanite iza riječi na koju se bilješka odnosi.
2. U izborniku {t:editor.insert} odaberite {t:command.footnote} ili {t:command.endnote}.
3. Upišite tekst bilješke. {t:command.noteBack} ({k:Escape}) vraća u tekst.

### Naredbe nad bilješkom

1. Stanite u bilješku. Na traci alata pojavljuje se izbornik {t:commandGroup.note}.
2. {t:command.toFootnote} i {t:command.toEndnote} mijenjaju vrstu bilješke.
3. {t:command.notesRestart} i {t:command.notesContinue} određuju brojeve bilježaka u kartici.
4. {t:command.deleteNote} briše bilješku i njezin broj u tekstu.

## Kako radi

Fusnote se broje 1, 2, 3, a završne bilješke i, ii, iii, svaka vrsta zasebno, redom kojim se čitaju. Ispod teksta kartice najprije su popisane fusnote, zatim završne bilješke. Čitači zaslona svaku bilješku najavljuju kao {t:note.foot} ili {t:note.end} s njezinim brojem.

Brojevi se nastavljaju iz prethodnih kartica, osim u kartici u kojoj ste odabrali da počnu od 1.

## Ograničenja

- Bilješka drži samo tekst u jednom odlomku: zalijepljeni sadržaj u njoj postaje običan tekst.
- U prvoj kartici brojevi uvijek počinju od 1.

## Povezano

- [Umetanje](help:text/insert)
- [Kartice](help:text/tabs)
- [Izvještaj o uvozu](help:documents/import)
