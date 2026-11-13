# Radnje nad tablicom

Radnje nad tablicom zbrajaju stupce, računaju novi stupac, čiste i grupiraju podatke te crtaju grafikon, bez slanja podataka izvan instalacije.

## Kako se koristi

### Zbroj i ukupno

1. Stavite kursor u tablicu i otvorite izbornik {t:commandGroup.table} na alatnoj traci ili desnim klikom.
2. Odaberite {t:action.tableTotals} za zbroj svih stupaca s brojevima.
3. Za jedan stupac stavite kursor u njega i u {t:action.tableTotal} odaberite {t:action.tableTotal.sum}, {t:action.tableTotal.average}, {t:action.tableTotal.count}, {t:action.tableTotal.counta}, {t:action.tableTotal.min}, {t:action.tableTotal.max} ili {t:action.tableTotal.none}.

### Izračunati stupac

1. Stavite kursor u prazan stupac i odaberite {t:action.tableCalculate.ask}
2. U dijalogu {t:action.tableCalculate}, pod {t:calculate.operation}, odaberite {t:action.tableCalculate.sum}, {t:action.tableCalculate.difference}, {t:action.tableCalculate.product}, {t:action.tableCalculate.quotient}, {t:action.tableCalculate.average}, {t:action.tableCalculate.min} ili {t:action.tableCalculate.max}.
3. Pod {t:calculate.columns} odaberite stupce redom kojim ulaze u račun; iznad se vidi formula.
4. Pritisnite {t:calculate.run}.

### Čišćenje, grupiranje i grafikon

1. {t:action.tableClean} uređuje podatke cijele tablice.
2. {t:action.tableGroup} grupira po stupcu u kojem je kursor.
3. {t:action.tableChart} crta grafikon iz označenih ćelija ili iz cijele tablice.

## Kako radi

{t:action.tableTotals} dodaje ispod podataka redak koji zbraja svaki stupac s brojevima, u obliku broja koji prevladava u stupcu. Ponovljena radnja obuhvaća retke koje podaci tada imaju. {t:action.tableTotal} upisuje odabranu funkciju u redak ukupno ispod stupca i stvara taj redak ako ga nema; stupcu koji nema samo brojeve nudi se samo {t:action.tableTotal.counta}.

Izračunati stupac upisuje formulu u svaki redak podataka, kao izračunati stupac u Excelu, a novi redak je nasljeđuje. {t:action.tableCalculate.difference} i {t:action.tableCalculate.quotient} uzimaju točno dva stupca, ostale radnje dva ili više.

{t:action.tableClean} uklanja razmake oko teksta i ponovljene razmake u njemu, brojeve zapisane kao tekst pretvara u brojeve i briše prazne retke i stupce. {t:action.tableGroup} razvrstava podatke po stupcu i ispod svake skupine dodaje redak s međuzbrojem ostalih stupaca s brojevima, a ispod svega redak ukupno. Ponovljeno grupiranje, po bilo kojem stupcu, najprije uklanja prijašnje skupine. {t:action.tableChart} dodaje stupčasti grafikon odmah iza tablice.

## Ograničenja

- Izračunati stupac upisuje se samo u prazan ili već izračunati stupac i računa samo sa stupcima koji sadrže brojeve.
- Stupac se ne može računati iz samoga sebe.
- Svaka od ovih radnji vraća se s {t:run.undo}.

## Povezano

- [Radnje i Claude](help:ai/actions)
- [Agent uz dokument](help:ai/agent)
- [Izvlačenje podataka iz dokumenata](help:ai/gathering)
