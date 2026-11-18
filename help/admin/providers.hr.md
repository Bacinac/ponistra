# Prijava pošte preko Googlea i Microsofta

Da bi se računi e-pošte kod Googlea i Microsofta prijavljivali preko pružatelja umjesto lozinkom, administrator ovdje unosi registraciju instalacije kod svakog od njih.

## Kako se koristi

1. Otvorite {t:admin.title} i odaberite {t:providers.title}.
2. Pod {t:providers.signIn}, uz {t:providers.google} ili {t:providers.microsoft}, pritisnite {t:providers.setUp}, odnosno {t:providers.change} kad je registracija već unesena. Dok nije, piše {t:providers.none}
3. Pritisnite {t:providers.copy} uz {t:providers.redirect} i kod pružatelja izradite registraciju aplikacije s tom adresom za povratak, kako opisuje uputa na vrhu obrasca.
4. Upišite {t:providers.clientId} i {t:providers.secret}, a za Microsoft i {t:providers.expires}.
5. Pritisnite {t:providers.save}.
6. Registraciju uklanjate gumbom {t:providers.remove} i potvrdom u dijalogu {t:providers.removeTitle}

## Kako radi

Tajna se sprema zaključana i više se ne prikazuje; piše samo {t:providers.secretKept} i njezina zadnja četiri znaka. Nova tajna upisana pri promjeni zamjenjuje dosadašnju, a prazno polje ostavlja je kakva jest. Uz registraciju piše i kada je {t:providers.changed}.

Microsoftova tajna ima rok. Trideset dana prije isteka ovdje se pojavljuje upozorenje da izradite novu tajnu, jer se inače računi prestaju prijavljivati. Kad se uklonjena registracija ponovno unese, računi koji se prijavljuju preko tog pružatelja nastavljaju preuzimati i slati poštu.

Na istoj se stranici uključuje i {t:mail.openedSetting}; oznaka se sprema odmah.

Upisivanje i uklanjanje klijenta upisuju se u [dnevnik](help:admin/journal), nikad sama tajna.

## Ograničenja

- Dok registracija nije unesena, računi kod tog pružatelja ne mogu se prijaviti preko njega.
- Ako se promijeni tajna instalacije, spremljena tajna pružatelja više se ne može pročitati i treba je unijeti ponovno.

## Povezano

- [Računi e-pošte](help:mail/accounts)
- [Pročitano unutar organizacije](help:mail/opened)
