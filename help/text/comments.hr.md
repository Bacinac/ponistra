# Komentari

Komentar se veže uz označeni tekst, a razgovor o njemu teče u bočnom panelu dok ga netko ne riješi.

## Kako se koristi

### Novi komentar

1. Označite tekst.
2. Na traci alata ili desnom tipkom miša odaberite {t:command.comment} ({k:Mod-Alt-m}).
3. U panelu {t:comment.list}, pod {t:comment.new}, napišite komentar i pošaljite ga.

### Odgovor i rješavanje

1. U zaglavlju dokumenta pritisnite {t:comment.list}. Uz gumb stoji broj neriješenih komentara otvorene kartice.
2. Pritisnite komentar da biste skočili na tekst uz koji je vezan.
3. Napišite odgovor i pritisnite {t:comment.reply}.
4. Pritisnite {t:comment.resolve} kad je pitanje riješeno, a {t:comment.reopen} da ga ponovno otvorite.

### Izmjena i brisanje

1. U izborniku vlastitog komentara odaberite {t:comment.edit} ili {t:comment.delete}.
2. Brisanje potvrdite u dijalogu {t:comment.deleteTitle}

### Zadatak iz retka

1. Stanite u redak ili označite riječi.
2. Na traci alata odaberite {t:command.task} i spremite zadatak.

## Kako radi

Panel prikazuje komentare otvorene kartice redom kojim stoje u tekstu. Riješeni komentari su skriveni, a {t:comment.showResolved} ih prikazuje s brojem; uz svaki piše {t:comment.resolved}, tko ga je riješio i kada. Komentar izmijenjen nakon slanja nosi oznaku {t:comment.edited}, a komentar iz uvezene datoteke oznaku {t:comment.imported} s imenom autora iz datoteke. Autor čiji je račun obrisan prikazuje se kao {t:comment.formerUser}. Kad je obrisan tekst uz koji je komentar vezan, komentar ostaje i to navodi.

Na PDF-u se komentar veže uz označeni tekst ili točku na stranici, pa se uz njega navodi {t:pdf.page} s brojem.

Zadatak iz retka preuzima označene riječi, ili cijeli redak, i poveznicu natrag na to mjesto u dokumentu.

## Ograničenja

- Komentirati može svatko tko može otvoriti dokument, a rješavati i ponovno otvarati samo oni koji ga smiju uređivati.
- Komentar mijenja i briše samo njegov autor. Razgovor nestaje kad se obriše njegov posljednji komentar.
- Na riješeni komentar ne može se odgovoriti dok se ponovno ne otvori.

## Povezano

- [Prijedlozi izmjena](help:text/proposals)
- [Bilješke PDF-a](help:pdf/notes)
- [Dijeljenje](help:documents/sharing)
