# Obrasci u PDF-u

PDF s obrascem ispunjava se izravno na stranici, a upisane vrijednosti dobivaju se u preuzetoj datoteci.

## Kako se koristi

1. Otvorite PDF s obrascem. Polja se prikazuju na njegovim stranicama.
2. Upisujte u polja, birajte s popisa i označavajte kućice.
3. Kad polje ne prihvati upisano, iznad stranica pojavljuje se obavijest. Gumb {t:form.notice.close} zatvara je.
4. Pritisnite {t:file.download}. Preuzeta datoteka sadrži upisane vrijednosti, a njezina polja ostaju polja obrasca.

## Kako radi

Upisane vrijednosti čuvaju se uz datoteku, pa ih svi koji imaju datoteku otvorenu vide odmah, a izvorna datoteka ostaje prazna. Skripte obrasca izvode se dok upisujete: izračunavaju polja i provjeravaju upisano. Njihove poruke o obliku polja, datumu i dopuštenom rasponu prikazuju se na jeziku sučelja, a ostale onako kako ih datoteka piše.

## Ograničenja

- Polja može mijenjati samo onaj tko smije uređivati datoteku. Ostali vide upisane vrijednosti, ali ih ne mogu mijenjati.
- Obrazac izrađen samo u formatu XFA ne može se ispunjavati.
- Polje za elektronički potpis prikazuje se, ali Ponistra ne potpisuje dokumente.
- Radnje obrasca koje ne vode na neko mjesto, poput ispisa ili spremanja koje traži skripta, Ponistra ne izvodi i to javlja.
- Kad skripta obrasca ne uspije, obavijest upozorava da izračunate vrijednosti možda nisu točne.
- U PDF zaštićen lozinkom upisane vrijednosti ne upisuju se.

## Povezano

- [PDF datoteke](help:pdf/viewer)
- [Bilješke i komentari u PDF-u](help:pdf/notes)
