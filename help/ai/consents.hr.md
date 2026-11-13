# Pristanci

Pod Pristancima određujete što od vašeg rada smije otići modelima izvan instalacije: rečenice iz tražilice, izgovoreno i poruke na drugim jezicima.

## Kako se koristi

1. Otvorite {t:settings.title} i odaberite {t:consents.title}.
2. Pod {t:consents.search} odaberite {t:consents.search.ask}, {t:consents.search.always} ili {t:consents.search.words}.
3. Uključite ili isključite {t:consents.speech}.
4. Uključite ili isključite automatski prijevod poruka na jeziku koji ne čitate.

## Kako radi

Rečenicu upisanu u tražilicu Claude može pretvoriti u filtre pretrage. Uz {t:consents.search.ask} Ponistra pita prije svakog slanja, a uz {t:consents.search.words} ništa ne šalje i traži po upisanim riječima.

Izgovoreno se šalje tvrtki OpenAI, koja ga vraća kao tekst. Pristanak za to daje svaki korisnik sam, pri prvom snimanju ili ovdje.

Uz uključen automatski prijevod poruka na jeziku koji ne čitate šalju se Claudeu na prijevod čim ih otvorite, a vaši odgovori na njih bez pitanja. Isti pristanak daje izbor {t:translation.consent.always} pri prvom prijevodu poruke.

## Ograničenja

- Dok umjetna inteligencija nije uključena za instalaciju, pristanci za Claudea su onemogućeni i piše: {t:consents.aiOff}
- Dok govor u tekst nije uključen za instalaciju, pristanak za govor je onemogućen i piše: {t:speech.off}
- Pristanak za radnje nad dokumentom daje se u samom dokumentu, ne ovdje.

## Povezano

- [Radnje i Claude](help:ai/actions)
- [Prijevod](help:ai/translation)
