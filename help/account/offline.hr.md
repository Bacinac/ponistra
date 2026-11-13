# Rad bez mreže

Uređaj označen za rad bez mreže čuva stablo mapa, dokumente i nedavnu poštu, pa ih otvarate, uređujete i pišete i kad mreže nema, a izmjene se spajaju s ostalima i poruke odlaze kad se mreža vrati.

## Kako se koristi

### Uključivanje na uređaju

1. Na uređaju koji želite koristiti bez mreže otvorite Postavke, pa {t:devices.mine}.
2. Pod {t:offline.title} pritisnite {t:offline.enable}.
3. Pričekajte da umjesto {t:offline.keeping} piše {t:offline.kept} s vremenom spremanja.

Dok nije uključeno, piše: {t:offline.off}

### Čuvanje određenog dokumenta

1. U popisu mape desnom tipkom miša ili dugim pritiskom otvorite izbornik dokumenta.
2. Odaberite {t:offline.mark}.
3. Kad dokument više ne treba biti na uređaju, u istom izborniku odaberite {t:offline.unmark}.

### Rad bez mreže

1. Otvorite Ponistru na označenom uređaju kao i inače, i bez mreže.
2. Otvorite mapu ili dokument i pišite.
3. Kad se mreža vrati, ne trebate učiniti ništa: izmjene se same šalju.

### Pošta bez mreže

1. Otvorite Poštu na označenom uređaju i čitajte nedavne poruke s njihovim privicima.
2. Pišite, odgovarajte i prosljeđujte kao i inače, pa pritisnite {t:mail.send}. Poruka čeka pod {t:mail.laterTitle} s oznakom {t:mail.queuedWaiting}; poruka zatvorena nedovršena čeka s oznakom {t:mail.queuedUnsent}. Dok pišete, ono što je napisano sprema se na uređaj, pa u prozoru za pisanje piše {t:mail.keptOnDevice}.
3. Kad se mreža vrati, poruke odlaze same, a nedovršene se spremaju u skice.
4. Poruku koja ne treba otići odbacite: pod {t:mail.laterTitle} desnom tipkom miša ili dugim pritiskom otvorite njezin izbornik i odaberite {t:mail.discard}.

### Isključivanje

1. U Postavkama otvorite {t:devices.mine}.
2. Pritisnite {t:offline.disable}. Sve što je uređaj spremio briše se s njega.

## Kako radi

Uređaj sprema u preglednik: stablo svih mapa do kojih imate pristup, dokumente koje ste nedavno otvarali, dokumente označene s {t:offline.mark} te samu aplikaciju, kako bi se otvorila bez mreže. Spremanje se ponavlja pri svakom otvaranju Ponistre, kad se mreža vrati i minutu nakon što se nešto u mapama promijeni. Ako spremanje ne uspije, piše {t:offline.failed} s razlogom, a uređaj zadržava ono što je spremio ranije.

Izmjene napravljene bez mreže čuvaju se na uređaju i, kad se mreža vrati, spajaju s izmjenama drugih kao kod istodobnog uređivanja: ništa se ne prepisuje.

Iz pošte uređaj sprema vaše račune, prvu stranicu svake mape, poruke iz zadnjih mjesec dana (najviše 200 najnovijih) s njihovim privicima do 25 MB i započetim odgovorima te poruke koje čekaju slanje. Poruka koju uređaj tako spremi ne broji se kao otvorena. Spremanje pošte ponavlja se i minutu nakon što stigne ili se promijeni pošta.

Poruka napisana bez mreže odlazi kroz isti red kao [poruke poslane kasnije](help:mail/later) i odlazi samo jednom, i kad se veza prekine usred predaje. Ako je poslužitelj odbije, pod {t:mail.laterTitle} piše razlog, a u izborniku poruke možete odabrati {t:mail.queuedAgain} ili {t:mail.discard}.

Bez mreže je onemogućeno sve što obavlja poslužitelj: pretraživanje (u polju za pretraživanje piše {t:offline.needed}), radnje i AI nad dokumentom, novi dokument, nova bilješka, premještanje, preimenovanje i brisanje u mapama te u pošti premještanje, brisanje, oznake, odgoda, čekanje odgovora, reakcije, pravila, postavke računa, prilaganje datoteka s računala, skeniranje i slike u tekstu poruke. Omogućuje se samo od sebe čim se veza s poslužiteljem vrati.

U popisu prijavljenih uređaja uređaj koji čuva dokumente nosi oznaku {t:offline.marked}, pa i vi i administrator vidite gdje postoje kopije.

## Ograničenja

Mapa bez preuzimanja nikada se ne sprema na uređaj, ni ono što je u njoj, a {t:offline.mark} je ondje onemogućeno.

Tablice izračunava poslužitelj, pa bez mreže rade samo tekstni dokumenti i prezentacije. Datoteke u mapama, poput PDF-a i slika, ne spremaju se.

Iz pošte se ne spremaju starije poruke, privici veći od 25 MB ni dijeljeni sandučići. Poruke napisane bez mreže brišu se s uređaja zajedno sa svime ostalim ako mu prijava istekne prije nego što odu.

Odjava briše sve što je uređaj spremio. Ako uređaj odjavite iz popisa prijavljenih uređaja ili mu prijava istekne, briše se sve čim se sljedeći put spoji s poslužiteljem.

Aplikacija se sprema samo iz izdane inačice; dok to ne uspije, Ponistra se bez mreže ne može ponovno učitati.

## Povezano

- [Prijavljeni uređaji](help:account/devices)
- [Dijeljenje](help:documents/sharing)
- [Slanje kasnije](help:mail/later)
