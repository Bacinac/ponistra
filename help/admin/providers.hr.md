# Prijava pošte preko Googlea i Microsofta

Da bi se računi e-pošte kod Googlea i Microsofta prijavljivali preko pružatelja umjesto lozinkom, administrator ovdje unosi registraciju instalacije kod svakog od njih.

## Kako se koristi

1. U {t:settings.title}, pod {t:settings.installation}, odaberite {t:providers.title}.
2. Pod {t:providers.signIn}, za {t:providers.google} ili {t:providers.microsoft}, pritisnite {t:providers.copy} uz {t:providers.redirect}.
3. Kod pružatelja izradite registraciju aplikacije s tom adresom za povratak, kako opisuje uputa ispod naziva pružatelja.
4. Upišite {t:providers.clientId} i {t:providers.secret}, a za Microsoft i {t:providers.expires}.
5. Pritisnite {t:providers.save}.
6. Registraciju uklanjate gumbom {t:providers.remove} i potvrdom u dijalogu {t:providers.removeTitle}

## Kako radi

Tajna se sprema zaključana i više se ne prikazuje; piše samo {t:providers.secretKept} i njezina zadnja četiri znaka. Nova tajna upisana u isto polje zamjenjuje dosadašnju, a prazno polje ostavlja je kakva jest. Uz registraciju piše i kada je {t:providers.changed}.

Microsoftova tajna ima rok. Trideset dana prije isteka ovdje se pojavljuje upozorenje da izradite novu tajnu, jer se inače računi prestaju prijavljivati. Kad se uklonjena registracija ponovno unese, računi koji se prijavljuju preko tog pružatelja nastavljaju preuzimati i slati poštu.

Na istoj se stranici uključuje i {t:mail.openedSetting}.

Upisivanje i uklanjanje klijenta upisuju se u [dnevnik](help:admin/journal), nikad sama tajna.

## Ograničenja

- Dok registracija nije unesena, računi kod tog pružatelja ne mogu se prijaviti preko njega.
- Ako se promijeni tajna instalacije, spremljena tajna pružatelja više se ne može pročitati i treba je unijeti ponovno.

## Povezano

- [Računi e-pošte](help:mail/accounts)
- [Pročitano unutar organizacije](help:mail/opened)
