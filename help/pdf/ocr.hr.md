# Prepoznavanje teksta

Stranice PDF-a koje nemaju teksta, poput skeniranih dokumenata, Ponistra sama čita i dodaje im tekst, pa se mogu pretraživati, a tekst odabrati i kopirati.

## Kako se koristi

1. Učitajte PDF u mapu. Prepoznavanje počinje samo, bez ikakve radnje.
2. Dok traje, uz broj stranice piše {t:ocr.waiting}
3. Kad završi, PDF se prikazuje s prepoznatim tekstom.
4. Ako javi {t:ocr.failed} pritisnite {t:ocr.retry} uz poruku.

## Kako radi

Čitaju se samo stranice bez teksta, na hrvatskom i engleskom jeziku. Prepoznati tekst ugrađuje se u kopiju datoteke koja se prikazuje, pretražuje i preuzima. Izvorna datoteka ostaje kakva je učitana: dobiva se naredbom {t:file.original} u izborniku stranice.

## Ograničenja

- Šifrirana i digitalno potpisana datoteka ne čita se, jer bi se time narušila njezina zaštita. Uz broj stranice tada piše razlog.

## Povezano

- [PDF datoteke](help:pdf/viewer)
- [Datoteke](help:files/overview)
