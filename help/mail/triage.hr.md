# Razvrstavanje u mape

Claude za odabrane poruke predlaže mapu u koju koja pripada, a vi premještate one prijedloge koje prihvatite.

## Kako se koristi

1. Odaberite poruke na popisu, najviše 50 odjednom (vidi [rad s više poruka](help:mail/selecting)).
2. U izborniku trake odabira ili retka odaberite {t:mail.triage}.
3. U dijalogu pristanka pritisnite {t:ai.consent.once}.
4. U dijalogu {t:mail.triageTitle} uz svaku poruku stoji predložena mapa. Uklonite kvačicu uz poruke koje ne želite premjestiti.
5. Pritisnite {t:mail.triageApply}.

## Kako radi

Claude dobiva pošiljatelja, predmet i početak teksta svake odabrane poruke te popis vaših mapa, a za svaku poruku bira jednu mapu ili je ostavlja gdje jest. Može predložiti vaše mape, arhivu i neželjenu poštu, ali ne pristiglu, poslanu poštu, skice, odgođene poruke ni smeće. Arhiva i neželjena pošta nastaju prvi put kad u njih nešto premjestite.

Ništa se ne premješta dok ne pritisnete {t:mail.triageApply}. Premještanje vrijedi samo u Ponistri, kao i svako drugo premještanje pošte. Kad Claude sve poruke ostavi gdje jesu, dijalog to kaže: {t:mail.triageNone}

Pristanak vrijedi samo za to razvrstavanje. Svako razvrstavanje ulazi u mjesečni strop umjetne inteligencije instalacije, a u pregledu potrošnje koji vide administratori stoji kao {t:action.mailTriage}.

## Ograničenja

- Radnja je onemogućena dok je umjetna inteligencija u instalaciji isključena ili kad je odabrano više od 50 poruka.
- Za razvrstavanje morate poruke odabrati jednu po jednu ili na stranici; odabir cijele mape ({t:explorer.selectAll}) ga ne nudi.
- U poslanoj pošti i skicama razvrstavanja nema.
- U zajedničkom sandučiću razvrstavanje traži ulogu koja dopušta uređivanje.

## Povezano

- [Rad s više poruka](help:mail/selecting)
- [Blokirani pošiljatelji i slike po domeni](help:mail/senders)
