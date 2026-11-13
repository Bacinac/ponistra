# Ploče

Ploča je HTML stranica koju otvarate u Ponistri, poput plana, praćenja ili pregleda, a najčešće je piše vanjski agent za vas.

## Kako se koristi

### Popis ploča

1. U lijevom stupcu Dokumenata otvorite [ploče](/boards).
2. Ploče su složene po grupama: najprije vaše grupe po nazivu, zatim vaše ploče bez grupe pod {t:links.ungrouped}, pa ploče koje drugi dijele s vama, po mjestu odakle dolaze.
3. Pritisnuta ploča prikazuje se uz popis, a dok nijednu ne odaberete, prva. Dvostrukim pritiskom ploča se otvara; na mobitelu je dovoljan jedan dodir.

### Grupiranje

1. Desni klik ili dugi pritisak na ploču otvara izbornik s {t:boards.group}
2. Upišite naziv grupe i pritisnite {t:tree.move}. Grupa tog naziva nastaje ako je još nema.

### Otvorena ploča

- Izbornik ploče nudi {t:file.open}, koji ploču otvara samu u novoj kartici, te {t:board.source} za njezin HTML; {t:board.shown} vraća prikaz.
- {t:access.share} otvara pristup ploči, kao kod svakog dokumenta.
- {t:version.list} prikazuje prijašnje stranice ploče, kako opisuju [verzije ploče](help:boards/versions).
- {t:board.agent} otvara razgovor s agentom u radnom prostoru za kod, kako opisuje [slanje ploče agentu](help:boards/agent).

## Kako radi

Ploču piše agent kojeg ste povezali s Ponistrom, kako opisuje članak [Što agent može](help:agents/tools). Na stranici Ploče su ploče iz vaše mape ploča, čije su podmape grupe, i ploče iz mapa ploča koje drugi dijele s vama.

Ploča se pokazuje odmah nakon što agent upiše novu stranicu. Ploča može čuvati vlastite podatke, primjerice kvačice popisa: čita ih svatko tko smije čitati ploču, a mijenja onaj tko je smije uređivati. Kad se ti podaci promijene, otvorena ploča čita ih ponovno.

Ploča je zatvorena u zasebnom okviru: ne vidi ništa drugo iz Ponistre, ne vodi nikamo i učitava samo biblioteke s nekoliko javnih poslužitelja.

## Ograničenja

- Stranica ploče je najviše 1 MB.
- Dok nemate nijedne ploče, piše: {t:boards.empty}

## Povezano

- [Verzije ploče](help:boards/versions)
- [Poveznica izvan instalacije](help:documents/outside)
- [Što agent može](help:agents/tools)
- [Slanje ploče agentu](help:boards/agent)
