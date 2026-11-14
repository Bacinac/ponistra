# Relej sastanaka

Administrator određuje vanjski TURN servis kroz koji slika i zvuk sastanka stižu do sudionika izvan mreže organizacije kad instalacija nema otvorenih portova prema unutra.

## Kako se koristi

### Cloudflare

1. Otvorite {t:admin.title} i odaberite {t:relay.title}.
2. Pod {t:relay.provider} odaberite Cloudflare.
3. Upišite {t:relay.keyId} i {t:relay.token} TURN ključa iz Cloudflareove nadzorne ploče.
4. Pritisnite {t:ai.save}.

### Drugi TURN servis

1. Pod {t:relay.provider} odaberite {t:relay.turn}.
2. Pod {t:relay.addresses} upišite adrese servisa, svaku u svoj redak, primjerice `turn:turn.example.com:3478` i `turns:turn.example.com:443?transport=tcp`.
3. Upišite {t:relay.username} i {t:relay.password}, pa pritisnite {t:ai.save}.

### Isključivanje

1. Pod {t:relay.provider} odaberite {t:relay.none}.
2. Pritisnite {t:ai.save}.

## Kako radi

Bez vanjskog releja preglednik dobiva ono što nudi poslužitelj sastanaka instalacije: izravnu vezu i, gdje je instalacija ima, vlastiti relej. Sudionici na mreži organizacije, ili spojeni na nju, sastanak imaju i bez ikakve postavke.

S vanjskim relejem svaki ulazak u sastanak, i člana i gosta, dobiva adrese i vjerodajnice releja umjesto releja poslužitelja sastanaka. Preglednik do releja dolazi prema van, a poslužitelj sastanaka se releju također javlja prema van, pa nijedan port prema instalaciji ne mora biti otvoren.

Uz Cloudflare instalacija od ključa i tokena traži vjerodajnice koje vrijede jedan dan i daje ih svakom ulasku. Nove traži kad starima ostane manje od 12 sati, pa vjerodajnice nikad ne isteknu usred sastanka. Prije spremanja instalacija ključ isproba kod Cloudflarea; neprihvaćen ključ se ne sprema.

Token ili lozinka čuvaju se zapečaćeni tajnom instalacije i ne prikazuju se više, osim zadnja 4 znaka uz {t:relay.kept}. Polje za token ili lozinku ostavite prazno da ostane spremljena vrijednost; kad promijenite pružatelja, morate je upisati ponovno. Isključivanje releja briše i spremljenu vrijednost. Svaka promjena upisuje se u [dnevnik](help:admin/journal), uz {t:ai.changed} na stranici.

## Ograničenja

- Postavku vidi i mijenja samo administrator instalacije.
- Dok je vanjski relej postavljen, a ne može se dobiti, ulazak u sastanak se odbija umjesto da sudionik uđe bez releja:
  - {t:error.relay_refused} Ključ je povučen ili token nema dopuštenje; upišite važeći.
  - {t:error.relay_unreachable} Instalacija ne dolazi do pružatelja; provjerite vezu instalacije prema van.
  - {t:error.relay_lost} Tajna instalacije se promijenila; upišite token ili lozinku ponovno.
- Nepotpuna postavka se ne sprema, nego piše jedno od:
  - {t:error.relay_name_needed}
  - {t:error.relay_address_needed}
  - {t:error.invalid_relay_address}
  - {t:error.relay_secret_needed}
- Poslužitelj sastanaka mora smjeti slati UDP promet prema van.

## Povezano

- [Gosti](help:meetings/guests)
- [Sastanci](help:meetings/overview)
- [Zdravlje instalacije](help:admin/health)
