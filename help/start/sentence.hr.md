# Pretraga rečenicom

Rečenicu upisanu u tražilicu Claude pretvara u riječi i filtre pretrage, pa ne morate pamtiti kako se filtri pišu.

## Kako se koristi

1. U kutiju za pretragu ili u polje na stranici {t:search.title} upišite rečenicu od barem 3 riječi, na primjer „ponude od Ane iz prošlog mjeseca”, i pritisnite {k:Enter}.
2. Prvi put otvara se pitanje {t:ai.consent.heading}. Odaberite {t:ai.consent.once} za ovu rečenicu, {t:search.consent.always} da se više ne pita, ili {t:search.consent.words} da se rečenica traži onakva kakva je upisana.
3. Dok Claude čita rečenicu, piše: {t:search.ai.translating}
4. Otvara se stranica rezultata s riječima i filtrima koje je Claude pročitao. Filtre mijenjate i uklanjate kao i one koje sami dodate.

## Kako radi

Rečenica odlazi modelu Claude tvrtke Anthropic u SAD-u samo kada je umjetna inteligencija uključena za instalaciju i vi ste na to pristali. Odlazi samo rečenica, ne i vaši dokumenti ni pošta. Claude iz nje izdvaja riječi koje se traže te vrstu, osobu, račun, mapu, razdoblje i privitak, a razdoblje poput „prošlog mjeseca” računa od današnjeg dana.

Tekst se šalje Claudeu samo ako ima barem 3 riječi i nijedna nije filtar, odnosno riječ s dvotočkom. Kraći tekst i tekst s filtrom traže se onakvi kakvi su upisani.

Odgovor za sve pretrage pamti se uz vaš račun. Mijenjate ga u [postavkama](/settings/ai), pod {t:consents.title}. Uz {t:search.consent.words} rečenice više ne odlaze nikamo i pitanje se više ne postavlja.

## Ograničenja

- Ako umjetna inteligencija nije uključena za instalaciju, rečenica se traži kao obične riječi.
- Ako Claude ne može pročitati rečenicu, ispod kutije se prikazuje razlog i gumb {t:search.ai.literal}, koji traži riječi onakve kakve su upisane.
- Claude može krivo pročitati rečenicu. Provjerite filtre na stranici rezultata i ispravite ih.

## Povezano

- [Rezultati pretrage i filtri](help:start/results)
- [Kutija za pretragu](help:start/search)
