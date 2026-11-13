# Prijava i način prijave

Na stranici {t:auth.title} ulazite u Ponistru lozinkom ili pristupnim ključem, a u postavkama birate što vam ta stranica nudi prvo.

## Kako se koristi

### Prijava

1. Otvorite adresu svoje instalacije. Dok niste prijavljeni, prikazuje se stranica {t:auth.title}.
2. Upišite {t:auth.email} i {t:auth.password}, pa pritisnite {t:auth.signIn}. Dok traje, gumb prikazuje: {t:auth.signingIn}
3. Umjesto lozinke možete pritisnuti {t:auth.passkey} i potvrditi otiskom prsta, licem ili PIN-om uređaja. Dok način prijave nije odabran, pristupni ključevi spremljeni na uređaju nude se i ispod polja za e-poštu čim ga otvorite.
4. Ako je administrator povezao izdavatelja prijave organizacije, stranica nudi i gumb s njegovim nazivom. Pritisnite ga, prijavite se kod izdavatelja i preglednik se vraća u Ponistru prijavljen.

### Način prijave

1. U Postavkama otvorite {t:signIn.choice}.
2. Odaberite {t:signIn.none}, {t:password.title} ili {t:signIn.passkey}.
3. Kad je odabran pristupni ključ, stranica prijave nudi samo gumb {t:auth.passkey}. Za prijavu lozinkom na njoj pritisnite {t:auth.withPassword}.

### Odjava

1. Pritisnite svoje inicijale u gornjem desnom kutu, {t:frame.account}.
2. Odaberite {t:auth.signOut}. Isto nudi i kutija za pretragu.

## Kako radi

Način prijave određuje samo što stranica prijave pokazuje prvo, ne i što je dopušteno. Račun ga pamti za sve uređaje, a preglednik čuva kopiju za stranicu prijave, koja ga tako zna i prije nego što se prijavite. {t:signIn.passkey} može se odabrati tek kad imate barem jedan pristupni ključ. Kad uklonite posljednji, izbor se vraća na {t:signIn.none}.

Svaka nova prijava javlja se obaviješću u preglednicima u kojima ste uključili obavijesti, a obavijest vodi na popis prijavljenih uređaja.

Odjava završava prijavu samo u tom pregledniku. Prijave na drugim uređajima ostaju.

Prijava u pregledniku ističe nakon 14 dana bez korištenja i najkasnije 30 dana nakon prijave, koliko god se preglednik koristio. Tada Ponistra ponovno traži prijavu.

Prijava kod izdavatelja mora završiti u pregledniku u kojem je počela i unutar 10 minuta. Ako prijavu odbije, Ponistra se vraća na stranicu prijave i ispod gumba piše zašto.

Administrator instalacije u njezinu dnevniku vidi svaku prijavu i svaku neuspjelu prijavu, s adresom s koje je došla.

## Ograničenja

- Kad e-pošta ili lozinka nisu točne, piše: {t:auth.invalid}
- Nakon 5 neuspjelih pokušaja s iste mrežne adrese za isti račun piše {t:auth.locked}
- Ako je administrator za vaš račun propisao prijavu pristupnim ključem, a ključ već imate, lozinka više nije dovoljna i stranica traži pristupni ključ.
- Kad izdavatelj vrati prijavu odbijenu, piše jedno od ovoga:
  - {t:auth.refused.no_account} Izvor ne izrađuje račune; račun vam izrađuje administrator.
  - {t:auth.refused.outside_domains} Prijavite se računom organizacije.
  - {t:auth.refused.unverified_email} {t:auth.refused.no_email} To se uređuje kod izdavatelja.
  - {t:auth.refused.inactive} Javite se administratoru.
  - {t:auth.refused.visitor} Posjetitelj ulazi samo svojom poveznicom.
  - {t:auth.refused.unknown_attempt} {t:auth.refused.expired_attempt}
  - {t:auth.refused.provider_refused} {t:auth.refused.provider_unreachable}
  - {t:auth.refused} Odgovor izdavatelja nije prošao provjeru; razlog administrator vidi u dnevniku.
- Kad vaš račun dolazi iz imenika organizacije, na ovoj se stranici prijavljujete adresom i lozinkom iz imenika ako ih je administrator tako povezao.
- Bez pristupnog ključa i lozinke ne možete se prijaviti sami. Ako ste izgubili uređaj s ključem, administrator vam može postaviti novu lozinku.

## Povezano

- [Pristupni ključevi](help:account/passkeys)
- [Lozinka](help:account/password)
- [Prijavljeni uređaji](help:account/devices)
