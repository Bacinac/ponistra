# Agent uz dokument

Agent je razgovor s Claudeom uz otvoreni dokument: svaka uputa izvodi se nad karticom koju gledate, a svaki korak razgovora možete zasebno poništiti.

## Kako se koristi

### Razgovor

1. Na traci dokumenta pritisnite {t:agent.title} ili u izborniku odaberite {t:action.textAsk.ask}
2. Ako se uputa odnosi na dio teksta, označite ga u dokumentu.
3. Upišite uputu i pritisnite {k:Enter} ili {t:agent.send}. Novi redak u uputi dobivate s {k:Shift-Enter}.
4. Dok Claude radi, pritisnite {t:run.stop} da stane nakon koraka na kojem jest.
5. Kad Claude ponudi odgovore na pitanje kako je uputa mišljena, pritisnite onaj koji vrijedi.
6. Pritisnite {t:agent.undo} ispod koraka da vratite sve što je taj korak promijenio. Korak tada nosi oznaku {t:agent.undone}.
7. Pritisnite {t:agent.new} za razgovor iznova, bez ranijih koraka.

### Analiza tablice

1. Stavite kursor u tablicu.
2. U izborniku {t:commandGroup.table} na alatnoj traci ili desnim klikom odaberite {t:action.tableAnalyse}.
3. Analiza se otvara u novoj kartici kad Claude završi.

## Kako radi

Claude čita karticu koju gledate, označene odlomke i ranije korake istog razgovora, pa uputa poput „sad kao tortni grafikon” mijenja ono što je napravio prethodni korak. Tekst koji napiše dolazi kao prijedlog, a oblikovanje, tablice i grafikoni mijenjaju se odmah. Kad se uputa može shvatiti na više načina koji vode različitim rezultatima, Claude ništa ne mijenja nego pita i nudi dva do četiri odgovora. Razgovor je vaš: drugi u dokumentu vide korak na traci radnje kao {t:action.textAsk}, ali ne i vaš razgovor. Kad ponovno otvorite panel, prikazuje se vaš zadnji razgovor u tom dokumentu.

Iz duge tablice Claude čita prvih 100 redaka, a ostale retke i pregled cijele tablice po stupcima (vrste vrijednosti, različite i najčešće vrijednosti, najmanji i najveći broj) dohvaća kad mu zatrebaju. Broj koji navodi nikad ne računa sam: upisuje formulu, čita što je izračunala i tek onda piše o njoj.

{t:action.tableAnalyse} otvara novu karticu nazvanu {t:agent.analysis} i nazivom izvorne kartice. U nju Claude upisuje naslov, tablice formula nad podacima izvorne tablice (zbrojeve, prosjeke, raspršenost, udjele po kategorijama, povezanost brojčanih stupaca), grafikone i kratak tekst o tome što pokazuju. Ako izvorna tablica nema naziv, dobiva naziv po kartici kako bi je formule mogle adresirati. Kad se podaci promijene, formule u analizi računaju iznova.

## Ograničenja

- Agent je dostupan samo onima koji smiju uređivati dokument, ne i vanjskim posjetiteljima.
- Uputa prima najviše 4000 znakova, a Claude čita najviše 20 ranijih koraka razgovora.
- Agent i analiza šalju sadržaj Claudeu i traže isto odobrenje kao ostale radnje s modelom.
- Dok jedan korak traje, sljedeći se ne može poslati.
- {t:agent.undo} na analizi zatvara novu karticu i uklanja naziv koji je tablica dobila.

## Povezano

- [Radnje i Claude](help:ai/actions)
- [Pisanje s Claudeom](help:ai/writing)
- [Radnje nad tablicom](help:ai/tables)
- [Prijedlozi](help:ai/proposals)
