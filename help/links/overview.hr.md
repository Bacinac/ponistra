# Poveznice

Poveznice su vaše spremljene web adrese, složene u grupe kao pločice s ikonom, nazivom i opisom.

## Kako se koristi

### Nova poveznica

1. U lijevom stupcu Dokumenata otvorite [poveznice](/links) i pritisnite {t:create.new}, zatim {t:create.link}.
2. Upišite {t:tree.address}, a po želji i {t:tree.name}.
3. Pritisnite {t:tree.create}.

### Grupe

- {t:create.new} pa {t:links.newGroup} izrađuje grupu.
- Izbornik u naslovu grupe nudi {t:create.link} u toj grupi, {t:tree.rename}, {t:links.columns} i {t:tree.toTrash}.
- Pod {t:links.columns} birate u koliko stupaca grupa slaže pločice, od jednog do šest, ili {t:links.columnsAuto}.
- Grupe i pločice premještate povlačenjem; poveznicu u drugu grupu premješta i {t:links.moveTo}, gdje {t:links.ungrouped} izvlači poveznicu iz grupe.

### Uređivanje poveznice

1. Desni klik na pločicu otvara izbornik s omiljenima, {t:tree.editLink}, {t:links.moveTo} i {t:tree.toTrash}.
2. U {t:tree.editLink} mijenjate adresu i naziv, a pod {t:links.icon} upisujete {t:links.iconName}, birate {t:links.removeIcon} ili {t:links.pickIcon}
3. Pritisnite {t:tree.save}.

Sliku ispuštenu na pločicu Ponistra uzima kao ikonu te poveznice. Za više poveznica odjednom dugo pritisnite jednu pa dodirom ili klikom dodajte ostale.

### Učitavanje poveznica

1. Pritisnite {t:create.new} pa {t:links.load} Datoteke možete i ispustiti na stranicu.
2. Odaberite oznake izvezene iz preglednika (HTML) ili Homepage nadzornu ploču (YAML), po želji zajedno sa slikama ikona.

### Početna stranica preglednika

1. Postavite [početnu stranicu poveznica](/start) kao početnu stranicu preglednika. Na njoj su samo vaše grupe i pločice, preko cijelog prozora.
2. Pločica otvara svoju adresu.
3. Logo vodi u Ponistru, a {t:links.edit} na stranicu poveznica, gdje se poveznice dodaju, premještaju i uređuju.

Ako niste prijavljeni, Ponistra najprije traži prijavu, a zatim otvara početnu stranicu poveznica.

## Kako radi

Pločica se otvara u novoj kartici. Adresu bez `https://` Ponistra dopunjuje sama. Nakon spremanja pročita stranicu i uzme njezin naslov, opis i ikonu, osim onoga što ste sami upisali; ako je stranica iza prijave, uzima samo ikonu web mjesta.

{t:links.iconName} prima adresu slike ili naziv ikone kako ga piše Homepage: naziv iz dashboard-icons, ili s predmetkom `sh-` (selfh.st), `mdi-` (Material Design) i `si-` (Simple Icons).

Pri učitavanju svaka grupa iz datoteke postaje grupa poveznica, a pridružuje se postojećoj istog naziva; poveznica čija je adresa već u grupi ne izrađuje se ponovno.

Poveznice su stavke vaših dokumenata, pa ih tražilica pronalazi. Ispod vaših grupa stoje i poveznice iz mapa tvrtke i mapa podijeljenih s vama; one koje smijete samo čitati ne možete urediti ni premjestiti.

## Ograničenja

- Adresa mora biti web adresa (`http` ili `https`).
- Jedno učitavanje donosi najviše 10.000 poveznica.
- Dok nema nijedne poveznice, piše: {t:links.empty}

## Povezano

- [Kutija za pretragu](help:start/search)
- [Ploče](help:boards/overview)
