# Prijava u aplikacije

Druge aplikacije vaše organizacije mogu svoje korisnike prijavljivati preko Ponistre, pa korisnik ondje ne treba zasebnu lozinku.

## Kako se koristi

### Nova aplikacija

1. U {t:settings.title}, pod {t:settings.installation}, odaberite {t:identity.title}.
2. Pritisnite {t:identity.new}.
3. Upišite {t:identity.name} i {t:identity.redirects}.
4. Pod {t:identity.who} odaberite {t:identity.who.everyone} ili {t:identity.who.admins}, pa pritisnite {t:tree.create}.
5. Kopirajte {t:identity.issuer}, {t:identity.clientId} i {t:identity.secret} i unesite ih u postavke aplikacije.

### Postojeća aplikacija

1. U retku aplikacije otvorite izbornik.
2. Odaberite {t:identity.edit}, {t:identity.renew} ili {t:identity.delete}.
3. Novu tajnu potvrdite u dijalogu {t:identity.renewTitle} Uklanjanje potvrdite u dijalogu {t:identity.deleteTitle}

## Kako radi

Ponistra je za te aplikacije izdavatelj prijave po standardu OpenID Connect. Kad aplikacija pošalje korisnika na prijavu, Ponistra ga prijavljuje odmah ako je već prijavljen, s naslovom koji imenuje aplikaciju i oznakom {t:identity.as} uz njegovo ime. Ako prijava ne uspije, korisnik je ponavlja gumbom {t:identity.continue}.

Aplikacija dobiva oznaku korisnika, a ako to zatraži i njegovu adresu e-pošte i ime. Tajna se prikazuje samo jednom, kad se izradi; nova tajna poništava dosadašnju. Popis pokazuje {t:identity.who} i {t:identity.used} za svaku aplikaciju, a dok aplikacije nema, piše: {t:identity.none}

Svaka promjena aplikacije i svaka prijava korisnika u nju upisuje se u [dnevnik](help:admin/journal), nikad sama tajna.

## Ograničenja

- Prijaviti se mogu samo aktivni korisnici, a uz {t:identity.who.admins} samo administratori.
- Aplikacija se vraća samo na adrese upisane pod {t:identity.redirects}.
- Uklonjena aplikacija više se ne može prijavljivati preko Ponistre.
- Izrada, izmjena i nova tajna mogu tražiti potvrdu da ste to vi.

## Povezano

- [Korisnici](help:admin/users)
