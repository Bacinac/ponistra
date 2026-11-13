# Potvrda identiteta

Prije osjetljive radnje Ponistra traži da ponovno pokažete da ste to vi, pristupnim ključem ili lozinkom.

## Kako se koristi

1. Pokrenite osjetljivu radnju, na primjer promjenu lozinke. Otvara se dijalog {t:confirm.title}.
2. Pritisnite {t:confirm.passkey} i potvrdite na uređaju.
3. Ili upišite {t:auth.password} i pritisnite {t:confirm.submit}.
4. Ili pritisnite gumb s nazivom izdavatelja prijave organizacije. Otvara se njegov prozor; kad se ondje prijavite, prozor se zatvara sam.
5. Radnja se nakon potvrde nastavlja sama.

## Kako radi

Potvrda vrijedi 10 minuta u tom pregledniku, pa se u tom vremenu ne traži ponovno. Za terminal, otvaranje radnog prostora, push i restart na stranici [Projekti](help:agents/projects) vrijedi 8 sati. Prijava se računa kao potvrda.

Potvrda se traži prije promjene lozinke, dodavanja i uklanjanja pristupnog ključa, izrade lozinke aplikacije i povezivanja telefona, odobrenja pristupa vanjskom agentu ili drugoj aplikaciji, izrade i ukidanja poveznice za osobe izvan instalacije, promjene, brisanja i izvoza sefa te dodavanja i uklanjanja otključavanja sefa pristupnim ključem. Administratoru se traži i prije radnji nad korisnicima i postavkama instalacije.

Dijalog nudi pristupni ključ kad ga račun ima i preglednik ga podržava, lozinku kad se smijete prijaviti lozinkom ili lozinkom iz imenika organizacije, a izdavatelja prijave kad je vaš račun s njim povezan. Izdavatelj tada uvijek ponovno traži prijavu, i kad ste kod njega već prijavljeni.

## Ograničenja

- Kad zatvorite dijalog bez potvrde, radnja se ne izvodi i piše da nije potvrđena.
- Ako vam je prijava pristupnim ključem obavezna, a ključ imate, lozinka se ne nudi.
- {t:confirm.none} Prikazuje se kad se račun ne smije prijaviti lozinkom, a pristupni ključ nema ili ga preglednik ne podržava. Potvrdite tada s uređaja na kojem je ključ.
- Nakon 5 netočnih lozinki piše {t:auth.locked}
- {t:confirm.blocked} Dopustite skočne prozore za adresu instalacije i pokušajte ponovno.
- {t:auth.refused.someone_else} Odjavite se kod izdavatelja i prijavite se svojim računom.

## Povezano

- [Pristupni ključevi](help:account/passkeys)
- [Lozinka](help:account/password)
