# Izvlačenje podataka iz dokumenata

Claude iz više dokumenata i PDF datoteka izvlači iste podatke u jednu tablicu, po jedan redak za svaki dokument, u novom dokumentu pokraj njih.

## Kako se koristi

1. U mapi odaberite dokumente, PDF datoteke ili mape.
2. Desnom tipkom miša ili pod tri točke na traci odabira odaberite {t:action.nodesExtract.ask}
3. U dijalogu {t:action.nodesExtract} upišite {t:tree.name} novog dokumenta; predložen je naziv odabrane stavke ili mape uz {t:gather.name}.
4. Pod {t:gather.columns} upišite nazive stupaca ili polje ostavite prazno.
5. Pritisnite {t:gather.run}.
6. Na traci radnje pritisnite {t:run.open} da otvorite novi dokument.

## Kako radi

Claude čita svaki odabrani dokument i PDF te one izravno u odabranim mapama, karticu po karticu ili stranicu po stranicu, i iz svakoga daje jedan redak. Bez zadanih stupaca Claude ih bira prema prvom dokumentu, a ostali ih slijede. Prva ćelija retka je naziv dokumenta, s poveznicom na njega.

Novi dokument nastaje u mapi odabranih stavki, a ako nisu u istoj mapi, na vrhu vaših dokumenata. Na traci radnje piše {t:run.through} i koliko je dokumenata obrađeno; nakon završetka {t:run.missed} navodi dokumente koji nisu obrađeni i zašto.

{t:run.undo} premješta novi dokument u smeće.

## Ograničenja

- Pritisak na {t:gather.run} ujedno je pristanak da se sadržaj odabranih dokumenata pošalje Claudeu, za to jedno izvođenje.
- Najviše 30 stupaca i 500 odabranih stavki.
- Radnja je onemogućena dok umjetna inteligencija nije uključena za instalaciju i za stavke u mapi bez preuzimanja.

## Povezano

- [Radnje i Claude](help:ai/actions)
- [Radnje nad tablicom](help:ai/tables)
- [Rad sa stavkama](help:documents/organising)
