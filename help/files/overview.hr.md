# Datoteke

Datoteka koja nije dokument Ponistre, poput PDF-a, slike, tekstne datoteke, videozapisa ili zvučnog zapisa, otvara se na vlastitoj stranici i prikazuje u pregledniku.

## Kako se koristi

1. U mapi pritisnite datoteku ili stanite na nju i pritisnite {k:Enter}.
2. Gumb {t:file.download} preuzima datoteku na računalo.
3. Izbornik stranice nudi {t:file.open}, koji datoteku otvara u novoj kartici preglednika.
4. Gumb {t:access.share} otvara dijeljenje datoteke.

## Kako radi

Što stranica prikazuje ovisi o vrsti datoteke:

- PDF se prikazuje stranicu po stranicu, s bilješkama, komentarima i obrascima.
- Slika se prikazuje cijela, uklopljena u prozor. Slike PNG, JPEG, WebP i AVIF mogu se i urediti.
- Tekstna datoteka prikazuje se samo za čitanje, s brojevima redaka i pretragom.
- Videozapis i zvučni zapis reproduciraju se u pregledniku. Kad ga preglednik ne može reproducirati, stranica to javlja i savjetuje preuzimanje.
- Ostale vrste Ponistra čuva, ali ne prikazuje: stranica pokazuje naziv, vrstu i veličinu datoteke te savjetuje preuzimanje.

Preuzeti PDF sadrži bilješke, komentare i upisane vrijednosti obrasca, a tekst prepoznat na stranicama bez teksta ostaje u njemu. Kad ih datoteka ima, izbornik nudi i {t:file.original}, koji preuzima datoteku kakva je bila učitana. Isto vrijedi za uređenu sliku: preuzima se slika s izmjenama, a {t:file.original} daje neuređenu.

## Ograničenja

- U mapi {t:confined.label} datoteka se ne može preuzeti ni otvoriti zasebno.
- Bilješke i upisane vrijednosti ne mogu se upisati u PDF zaštićen lozinkom. Kad takva datoteka ima bilješke, gumb za preuzimanje glasi {t:file.original} i preuzima datoteku bez njih.

## Povezano

- [PDF datoteke](help:pdf/viewer)
- [Uređivanje slike](help:files/image-editor)
- [Tekstne datoteke](help:files/text)
- [Učitavanje datoteka](help:documents/upload)
