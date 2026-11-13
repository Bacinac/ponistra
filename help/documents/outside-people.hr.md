# Dijeljenje s osobom izvana

Vlasnik dijeli stavku s osobom bez računa u instalaciji po njezinoj adresi e-pošte, za čitanje ili uređivanje, i ona je otvara pod svojim imenom.

## Kako se koristi

### Dijeljenje

1. U izborniku stavke ili u zaglavlju otvorene stavke pritisnite {t:access.share}.
2. U odjeljku {t:outside.title} pritisnite {t:outside.person}.
3. Upišite {t:outside.name} i {t:outside.address} osobe.
4. Pod {t:access.role} odaberite {t:access.role.read} ili {t:access.role.edit}.
5. Isključite {t:outside.download} ako stavka smije ostati samo u pregledniku.
6. Pritisnite {t:outside.share} ili {t:tree.cancel}.

Osoba se zatim pojavljuje među ostalima s pristupom, označena kao {t:access.outside} uz svoju adresu. Ondje joj vlasnik mijenja ulogu, uključuje ili isključuje {t:outside.download} i uklanja pristup, kao i kolegi ([Dijeljenje](help:documents/sharing)).

### Otvaranje

1. Osoba dobiva poruku s poveznicom i otvara je u pregledniku, bez računa i lozinke.
2. Stavka se otvara u Ponistri, a osoba je u tom pregledniku prijavljena pod svojim imenom.

## Kako radi

Poruka odlazi s vašeg zadanog računa pošte (SMTP), na jeziku na kojem koristite Ponistru, i ostaje u vašim poslanim porukama. U njoj su naslov stavke, uloga i osobna poveznica te osobe. Ako poruka ne ode, dijeljenje se poništava.

Osoba dobiva račun posjetitelja koji nema lozinku: ulazi samo kroz svoje poveznice i ne može se prijaviti na stranici za prijavu. Ne vidi module, tražilicu ni osobe instalacije, a stranice koje ne smije otvoriti vraćaju je na {t:tree.shared}. Ondje su sve stavke koje su s njom podijeljene, od svih vlasnika. Pristup dijeljen sa svima ili sa skupinom do nje nikad ne dolazi.

Uz ulogu {t:access.role.edit} uređuje i komentira kao kolega, a u dokumentu, [dnevniku pristupa](help:documents/sharing) i prisutnosti drugih stoji njezino ime. Uz {t:outside.download} smije preuzeti, izvesti i ispisati stavku.

Prijava u pregledniku traje najdulje 30 dana, a ponovno otvaranje iste poveznice je obnavlja. Uklanjanjem pristupa poveznica prestaje vrijediti odmah, i u pregledniku u kojem je osoba već prijavljena.

## Ograničenja

- Dijeli samo vlasnik stavke, i to samo ako mu to dopušta politika instalacije. Inače piše {t:error.links_not_allowed}
- Adresa korisnika instalacije se odbija: {t:error.colleague} Kolegi pristup dajete u [dijeljenju](help:documents/sharing).
- Bez računa pošte koji šalje (ActiveSync ne šalje) poruka nema otkud otići: {t:error.no_account}
- Dijeljenja nema za stavku u mapi bez preuzimanja ni za spremljenu poveznicu na web.
- Poveznica koja više ne vrijedi javlja {t:error.no_link}
- Osoba izvana ne može dijeliti dalje, stvarati stavke, čitati poštu, kontakte ni kalendar. Takvi zahtjevi javljaju {t:error.visitors_not_allowed}

## Povezano

- [Dijeljenje](help:documents/sharing)
- [Poveznica izvan instalacije](help:documents/outside)
- [Dokumenti u pošti kao poveznice](help:mail/shared-links)
- [Podijeljeno](help:documents/shared)
