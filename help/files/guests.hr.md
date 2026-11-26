# Datoteke gostiju na računalima

Kontejneri i virtualni strojevi na računalima s Ponistra OS-om kojima upravljate otvaraju se u {t:rail.files} kao mape, pa se s njihovim datotekama radi ondje gdje jesu, bez kopiranja i bez prijave u gosta.

## Kako se koristi

1. Na traci modula pritisnite {t:rail.files}.
2. U lijevom stupcu otvorite {t:files.computers}; ispod su računala kojima upravljate.
3. Otvorite granu računala; ispod su njegovi gosti, kontejneri i virtualni strojevi. Isti gosti stoje na stranici {t:rail.files} dok nijedna mapa nije otvorena, kao naziv računala i gosta.
4. Pritisnite gosta. Otvara se na vrhu njegova datotečnog sustava, a mapa se otvara pritiskom na njezin redak.

Otvaranje, uređivanje, nove mape, učitavanje, preuzimanje, preimenovanje, premještanje, brisanje i kopiranje rade kao na [lokaciji na mreži](help:files/network). Svojstva stavke nude i vlasnika i prava (Unix).

## Kako radi

Ponistra ne otvara vezu prema gostu nego traži od računala da je otvori: računalo je stalno povezano s Ponistrom i kroz tu vezu šalje datoteke gosta. Zato gost ne treba ni SSH ni javnu adresu, a računalo može biti iza NAT-a.

Gost se otvara kao njegov administrator (root), pa se vidi i mijenja sve što je u njemu. Zato ga Ponistra nudi samo onima koji upravljaju računalom u Računalima. Gost koji ima vlasnika, kao radni prostor jedne osobe, otvara se samo tom vlasniku; ni upravitelju računala ga računalo ne otvara.

Kontejner se otvara i kad ne radi. Virtualni stroj otvara se samo dok radi, kroz Incus agenta u njemu.

Svako otvaranje računalo bilježi kao zadatak s vašim računom. Veza se zadržava 2 minute nakon zadnjeg zahtjeva, pa sljedeća mapa ne čeka novu.

Popis gostiju računala čita se kad otvorite {t:rail.files} i ponovno nakon jedne minute. Gosti koji se još izrađuju ili čija izrada nije uspjela ne pokazuju se. Računalo koje nije na vezi pokazuje grešku ispod svoje grane, a ostala rade dalje.

Brisanje u gostu je trajno: Ponistrino smeće ga ne čuva. Prva promjena može tražiti [potvrdu da ste to vi](help:account/confirm).

## Ograničenja

- {t:files.computers} vidi samo onaj tko upravlja barem jednim računalom.
- Windows virtualni stroj nema Incus agenta, pa mu se datoteke ne otvaraju.
- {t:error.guest_offline} Računalo je ugašeno ili nema mrežu; pokušajte kad se ponovno poveže.
- {t:error.guest_not_running} Pokrenite ga u Računalima ili pričekajte da mu se agent podigne.
- {t:error.guest_owned} Otvara ih samo vlasnik gosta.
- {t:error.guest_missing} Gost je u međuvremenu obrisan ili preimenovan; osvježite popis.
- {t:error.guest_unavailable} Na računalu ne radi Incus; stanje računala vidi se u Računalima.
- {t:error.guest_refused} Računalo je odbilo iz drugog razloga, koji bilježi u zadacima.
- {t:error.location_unreachable} i {t:error.location_closed} znače da je veza s računalom prekinuta; pokušajte ponovno.

## Povezano

- [Datoteke na mreži](help:files/network)
- [Datoteke](help:files/manager)
