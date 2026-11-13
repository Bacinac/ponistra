# Povezivanje vanjskog agenta

Vanjski agent, poput Claudea, ChatGPT-a ili drugog MCP klijenta, prijavljuje se preko vašeg računa i radi u Ponistri s vašim pravima.

## Kako se koristi

### Povezivanje

1. Otvorite {t:settings.title} i odaberite {t:agents.title}.
2. Pritisnite {t:agents.copy} uz {t:agents.url}.
3. U agentu dodajte tu adresu kao MCP poslužitelj.
4. Agent otvara stranicu {t:agents.consent.title} u pregledniku. Ako niste prijavljeni, najprije se prijavite.
5. Provjerite tko traži pristup, pod {t:agents.consent.as} svoj račun i pod {t:agents.consent.returns} adresu na koju se prijava vraća. Ispod {t:agents.consent.can} piše što će agent smjeti.
6. Pritisnite {t:agents.consent.allow} ili {t:agents.consent.deny}.

### Opoziv

1. Pod {t:agents.title} pronađite agenta u popisu.
2. Pritisnite {t:agents.revoke} i potvrdite u dijalogu {t:agents.revokeTitle}

## Kako radi

Agent djeluje kao vi: vidi dokumente, poštu, kalendar, zadatke i kontakte koje vi vidite i ništa više. Što upiše u dokument dolazi kao prijedlog s njegovim imenom uz vaše, odgovor koji sastavi čeka da ga vi pošaljete, a radnje koje pokrene vidite kao i svoje. Agent ništa ne briše i ne šalje poštu.

Popis pod {t:agents.title} ima stupce {t:agents.client}, {t:agents.connected} i {t:agents.used}. Kad agenta opozovete, više ne može čitati ni upisivati, a ono što je upisao ostaje.

Kad agent pokrene radnju koju izvodi Claude, ne traži se zasebno odobrenje dokumenta: pristanak je dan pri povezivanju agenta.

## Ograničenja

- Za {t:agents.consent.allow} Ponistra može tražiti potvrdu da ste to vi.
- Agent ne prihvaća i ne odbija prijedloge; to radite vi.
- Kad nijedan agent nije povezan, piše: {t:agents.none}

## Povezano

- [Što agent može](help:agents/tools)
- [Prijedlozi](help:ai/proposals)
- [Potvrda identiteta](help:account/confirm)
