# Verzije

Ponistra sama sprema verzije dokumenta dok ga uređujete, a možete spremiti i vlastitu, imenovanu verziju, pregledati svaku i vratiti dokument na nju.

## Kako se koristi

### Pregled verzija

1. U zaglavlju dokumenta pritisnite gumb {t:version.list} ili ga odaberite u izborniku dokumenta.
2. U bočnom popisu pritisnite verziju. Otvara se onakva kakva je bila, s oznakom {t:version.readOnly}
3. Kartice verzije otvarate kao i kartice dokumenta.

### Spremanje i imenovanje

1. U popisu verzija pritisnite {t:version.save}, upišite naziv i pritisnite {t:tree.save}.
2. Da biste automatskoj verziji dali naziv, desnom tipkom miša ili dugim pritiskom na nju otvorite izbornik i odaberite {t:version.name}. Imenovanoj verziji naziv mijenjate pomoću {t:tree.rename}.

### Vraćanje

1. Otvorite verziju ili otvorite njezin izbornik u popisu.
2. Pritisnite {t:version.restore} i potvrdite u dijalogu {t:version.restoreTitle}

### Usporedba s verzijom

1. Naredbom {t:action.documentCompare} otvara se dijalog u kojem pod {t:compare.version} odaberete verziju.
2. Pritisnite {t:compare.run}. Razlike stižu u dokument kao prijedlozi izmjena.

## Kako radi

Automatska verzija nastaje kad izmjene zastanu deset minuta, a najkasnije sat vremena nakon prve nespremljene izmjene. U popisu se zove {t:version.automatic}, imenovana nosi svoj naziv, a verzija nastala vraćanjem zove se po broju verzije iz koje je vraćena. Ispod naziva stoje broj verzije, vrijeme i imena onih koji su je uređivali.

Imenovane verzije čuvaju se trajno. Od automatskih se čuvaju sve iz posljednjeg dana, za posljednjih trideset dana posljednja svakog dana, a za starije posljednja svakog tjedna.

Vraćanje najprije sprema trenutno stanje kao novu verziju, pa ništa ne gubite. Dokument zatim dobiva kartice kakve su bile u verziji: one koje su nedostajale vraćaju se, a kasnije dodane uklanjaju se. Otvorene sesije uređivanja zatvaraju se.

## Ograničenja

- Spremanje, imenovanje i vraćanje traže pravo uređivanja. Uz pravo čitanja verzije možete samo pregledavati.
- Verzija se ne može mijenjati, samo pregledati ili vratiti.
- Dok dokument nema nijednu verziju, popis to i kaže: prva nastaje sama kad izmjene zastanu.

## Povezano

- [Prijedlozi izmjena](help:text/proposals)
- [Izvještaj o uvozu](help:documents/import)
- [Pregled dokumenata](help:documents/overview)
