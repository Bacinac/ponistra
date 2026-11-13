# Usporedba s datotekom

Uspoređuje karticu s datotekom programa Word ili drugim dokumentom i svaku razliku upisuje kao prijedlog izmjene, na primjer kad partner vrati ugovor bez praćenja promjena.

## Kako se koristi

1. Otvorite karticu koju uspoređujete.
2. Desnim klikom otvorite izbornik i odaberite {t:action.fileCompare.ask}
3. U dijalogu {t:action.fileCompare} odaberite dokument ili datoteku programa Word iz mapa, počevši od mape u kojoj je dokument.
4. Za datoteku koja je samo na računalu pritisnite {t:file.fromComputer} i odaberite je.
5. Razlike se pojavljuju u kartici kao prijedlozi. Prihvatite ili odbijte svaki zasebno, ili sve odjednom.

## Kako radi

Datoteka se čita kao pri uvozu, ali iz nje ne nastaje novi dokument. Datoteka odabrana s računala sprema se kakva jest u mapu u kojoj je dokument, pa ostaje uz njega. Uspoređuju se datoteke DOCX, DOCM, DOTX, DOTM, ODT, DOC i RTF te tekstni dokumenti Ponistre; od drugog dokumenta uzima se kartica istog naziva, a ako je nema, prva kartica.

Razlike pronalazi program, bez umjetne inteligencije, pa tekst ne napušta instalaciju. Uspoređuje se tekst odlomaka, naslova i tablica; razmaci i prazni odlomci ne računaju se kao razlika. Odlomak s promijenjenim riječima postaje jedan prijedlog u kojem su izbrisane i umetnute samo riječi koje se razlikuju. Odlomak kojeg u datoteci nema predlaže se za brisanje. Odlomci kojih ima samo u datoteci predlažu se za umetanje na mjestu na kojem stoje u datoteci, svaki niz uzastopnih kao jedan prijedlog, s vrstom odlomka, popisom i podebljanim, kosim, podcrtanim ili precrtanim tekstom iz datoteke, a izgledom ovog dokumenta. Tablica koja se razlikuje predlaže se za brisanje, a tablica iz datoteke za umetanje iza nje.

Autor svih prijedloga je naziv datoteke, a datum vrijeme usporedbe. Usporedba se može poništiti kao i druge radnje.

## Ograničenja

- Usporedbu može pokrenuti tko smije uređivati dokument i čitati datoteku.
- Slike, grafikoni i PDF-ovi u kartici ne uspoređuju se, a premješteni odlomak prikazuje se kao brisanje na starom mjestu i umetanje na novom.
- Ako kartica već ima prijedloga, javlja se {t:error.proposed}
- Ako su tekstovi isti, javlja se {t:error.same_as_file}
- Ako datoteka nije tekstni dokument ni datoteka programa Word, javlja se {t:error.not_comparable}
- Ako je datoteka oštećena, javlja se {t:error.unreadable}

## Povezano

- [Prijedlozi izmjena](help:text/proposals)
- [Pisanje s Claudeom](help:ai/writing)
- [Verzije](help:documents/versions)
