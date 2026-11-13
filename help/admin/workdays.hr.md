# Neradni dani

Administrator određuje državu i regiju čiji praznici vrijede u instalaciji, radno vrijeme te dane kad tvrtka ne radi.

## Kako se koristi

### Država i praznici

1. U {t:settings.title}, pod {t:settings.installation}, odaberite {t:workdays.title}.
2. Odaberite {t:workdays.country} i, gdje se praznici razlikuju po regijama, {t:workdays.subdivision} ili {t:workdays.wholeCountry}.
3. Pod {t:workdays.holidays} provjerite praznike koji iz toga slijede.

### Radno vrijeme

1. Pod {t:workdays.hours} upišite {t:workdays.opens} i {t:workdays.closes}.
2. Izađite iz polja. Promjena se sprema odmah.

### Neradni dani tvrtke

1. Pritisnite {t:workdays.new}.
2. Upišite {t:workdays.name} te datume {t:workdays.first} i {t:workdays.last}, pa pritisnite {t:tree.create}.
3. Za više dana odjednom odaberite {t:workdays.import} i datoteku kalendara.
4. Označite događaje koji su neradni dani i pritisnite {t:workdays.importChosen}.
5. U retku neradnog dana pritisnite {t:workdays.edit} ili {t:workdays.delete}; brisanje potvrdite u dijalogu {t:workdays.deleteTitle}

## Kako radi

Vikend i praznici odabrane države, a gdje se razlikuju i regije, neradni su dani instalacije. Pod {t:workdays.closures} upisujete dane kad tvrtka ne radi iako nisu praznici, poput kolektivnog godišnjeg odmora; popis uz svaki prikazuje {t:workdays.name} i {t:workdays.days}. Prema svim tim danima pomiču se ili preskaču ponavljanja nizova koji paze na neradne dane.

{t:workdays.hours} vrijedi za radne dane instalacije, po vremenu instalacije, a zadano je od 8 do 16 sati. Prema njemu kalendar nudi slobodne termine kad netko od pozvanih nije slobodan; ponavljanja nizova ne pomiče.

Iz datoteke kalendara nude se samo dani koji još nisu upisani, svi unaprijed označeni. Obrisan neradni dan ponovno postaje radni.

## Ograničenja

- Kad u datoteci nema novih dana, piše: {t:workdays.importNone}
- Dok nema nijednog neradnog dana tvrtke, piše: {t:workdays.none}
- Radno vrijeme koje ne završava nakon što počne ne sprema se, nego piše: {t:error.invalid_hours}

## Povezano

- [Ponavljajući događaji](help:calendar/recurring)
- [Sobe i resursi](help:admin/resources)
