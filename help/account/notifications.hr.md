# Obavijesti

Ponistra javlja novu poštu, poruku koja nije otišla u zakazano vrijeme, poruku na koju nitko nije odgovorio do zadanog datuma, automatski odgovor koji nije poslan, poruke u razgovorima i pozive u sastanak i kad nije otvorena, u pregledniku ili u instaliranoj aplikaciji.

## Kako se koristi

### Obavijesti u ovom pregledniku

1. U Postavkama otvorite {t:notifications.title}.
2. Pod {t:notifications.thisBrowser} pritisnite {t:notifications.enable}.
3. Preglednik pita smijete li primati obavijesti. Dopustite ih.
4. Stanje piše ispod naslova: {t:notifications.on} ili {t:notifications.off}
5. Za prestanak pritisnite {t:notifications.disable}.

### Instalirana aplikacija

1. Pod {t:notifications.installTitle} pritisnite {t:notifications.install} ako ga preglednik nudi.
2. Ako ga ne nudi, instalirajte aplikaciju iz izbornika preglednika, kako stranica opisuje.
3. Kad je aplikacija instalirana, piše: {t:notifications.installed}

### Drugi preglednici

1. Pod {t:notifications.browsers} su svi preglednici u kojima ste uključili obavijesti: {t:notifications.browser}, {t:notifications.since} i {t:notifications.last}.
2. Uz preglednik koji više ne koristite pritisnite {t:notifications.remove}.

## Kako radi

Obavijest putuje šifrirana kroz push-servis preglednika i samo je taj preglednik može pročitati. Pritisak na obavijest otvara poruku, razgovor ili sastanak. Dok je neki prozor Ponistre na tom uređaju vidljiv, obavijest se ne prikazuje. Obavijesti stižu i o novoj prijavi u vaš račun, novom pristupnom ključu i novoj lozinci aplikacije, administratoru i o problemu instalacije, koji otvara stranicu stanja sustava, a vlasniku mape o datoteci koja je u nju stigla kroz poveznicu za slanje datoteka, a ta obavijest otvara samu datoteku. Vlasnik radnog prostora za kod dobiva obavijest kad chat kruga čeka njegovu odluku, kad su svi chatovi kruga gotovi, kad je krug objedinjen i čeka push, kad je koordinator kruga završio korak s porukom ili čeka njegov unos, kad provjera u pregledniku ili noćna provjera nije prošla te kad tjedni limit pretplate ili limit modela prijeđe 80 % ili model počne trošiti kredite; ta obavijest otvara stranicu Projekti, u njezinu zasebnom prozoru ako je otvoren. Obavijest o chatu ili koordinatoru koji čeka odluku nosi gumbe {t:workspace.yes} i {t:workspace.no}, koji odgovaraju bez otvaranja Ponistre. Vlasnik dobiva obavijest i o novom prijedlogu za [memoriju agenta](help:agents/memory); obavijest o jednom prijedlogu nosi iste gumbe, koji ga prihvaćaju ili odbijaju, a obavijest o više njih kaže koliko ih je. Kad analiza prijedloga složi prijedloge u skupine, stiže obavijest s brojem skupina. Sve tri otvaraju karticu {t:workspace.view.memory} na stranici Projekti.

Uključivanje vrijedi samo za preglednik u kojem ga napravite. Preglednik koji nikad nije primio obavijest ima oznaku {t:notifications.never}, a onaj u kojem gledate popis {t:notifications.this}. Njega ne uklanjate s popisa nego isključivanjem obavijesti.

Na iPhoneu i iPadu obavijesti rade samo iz aplikacije dodane na početni zaslon, pa stranica do tada to i piše.

Administrator na ovoj stranici vidi i {t:notifications.setting}: prekidačem {t:notifications.settingOn} uključuje ili isključuje obavijesti za cijelu instalaciju, a ispod piše {t:notifications.settingChanged} s imenom i vremenom. Isključivanjem se brišu obavijesti koje su čekale na slanje, a dok je isključeno, ništa ne odlazi push-servisima.

## Ograničenja

- {t:notifications.unsupported}
- Kad je administrator isključio obavijesti za instalaciju, gumb za uključivanje se ne nudi, a piše: {t:notifications.offInstallation}
- Kad je preglednik zabranio obavijesti, gumb se ne nudi, a piše: {t:notifications.blocked}
- Dok nijedan preglednik ne prima obavijesti, piše: {t:notifications.none}

## Povezano

- [Prijavljeni uređaji](help:account/devices)
- [Postavke](help:account/settings)
