# Poveznica izvan instalacije

Vlasnik dokumenta, datoteke, ploče ili mape izrađuje poveznicu kojom ih čita i netko bez računa u instalaciji, s rokom i lozinkom po želji.

## Kako se koristi

### Izrada poveznice

1. U izborniku stavke ili u zaglavlju otvorene stavke pritisnite {t:access.share}.
2. U odjeljku {t:outside.title} pritisnite {t:outside.make}.
3. Za mapu pod {t:outside.kind} ostavite {t:outside.kind.open}. Druga vrsta, {t:outside.kind.upload}, opisana je u članku [Zatražene datoteke](help:documents/asked-files).
4. Po želji odaberite datum pod {t:outside.until} i upišite {t:outside.password}.
5. Isključite {t:outside.download} ako stavka smije ostati samo u pregledniku.
6. Pritisnite {t:outside.make} ili {t:tree.cancel}.
7. Uz poveznicu pritisnite {t:outside.copy} i pošaljite je osobi kojoj je namijenjena.

Uz svaku poveznicu piše njezina vrsta, do kada vrijedi ili {t:outside.always}, te {t:outside.withPassword} i {t:outside.noDownload} kad vrijede. Poveznica vrste {t:outside.kind.people} nastaje kad se dokument pošalje poštom kao poveznica i uz nju su adrese primatelja ([Dokumenti kao poveznice](help:mail/shared-links)). {t:outside.end} odmah ukida bilo koju od njih.

### Otvaranje poveznice

1. Osoba otvara poveznicu u pregledniku, bez prijave, i stavka se otvara u Ponistri.
2. Ako poveznica traži lozinku, piše {t:outside.asked} Osoba upisuje lozinku i pritišće {t:outside.open}.

## Kako radi

Tko otvori poveznicu, u tom pregledniku ostaje prijavljen kao posjetitelj te poveznice, najdulje 30 dana. Vidi samo tu stavku, a za mapu i sve u njoj, u stanju u kojem su sada, i može ih samo čitati i komentirati. Ne vidi ostatak Ponistre: ni module, ni tražilicu, ni osobe instalacije, a stranice koje ne smije otvoriti vraćaju ga na {t:tree.shared}. Uz {t:outside.download} smije i preuzeti, izvesti i ispisati stavku, a bez toga je čita samo u pregledniku.

Svi koji otvore istu poveznicu dijele istog posjetitelja, pa se u [dnevniku pristupa](help:documents/sharing) svako otvaranje bilježi kao {t:log.openedThroughLink}, a osoba kao {t:log.outsider}. Izrada poveznice bilježi se kao {t:log.linkMade}, a ukidanje kao {t:log.linkEnded}.

Korisnik instalacije koji već smije čitati stavku i otvori poveznicu dok je prijavljen, otvara stavku pod svojim imenom.

Poveznica prestaje vrijediti na kraju odabranog dana, kad je vlasnik ukine, kad stavka ode u smeće ili se premjesti u mapu bez preuzimanja, i kad administrator odredi da nitko ne smije dijeliti izvan instalacije. Ukidanjem se odjavljuje i svatko tko je kroz nju ušao.

## Ograničenja

- Poveznicu izrađuje samo vlasnik stavke, i to samo ako mu to dopušta politika instalacije. Inače piše {t:error.links_not_allowed}
- Poveznica s rokom koji je već prošao ne izrađuje se: {t:error.invalid_link_date}
- Poveznice nema za stavku u mapi bez preuzimanja ni za spremljenu poveznicu na web.
- Nakon 10 krivih lozinki poveznica 15 minuta ne prima nove pokušaje: {t:error.too_many_link_tries}
- Poveznica koja više ne vrijedi javlja {t:error.no_link}
- Korisnik instalacije bez prava na stavku dobiva {t:error.signed_in_inside} Poveznica je namijenjena osobama izvana; pristup mu daje vlasnik u [dijeljenju](help:documents/sharing).

## Povezano

- [Dijeljenje](help:documents/sharing)
- [Dijeljenje s osobom izvana](help:documents/outside-people)
- [Zatražene datoteke](help:documents/asked-files)
