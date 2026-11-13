# Dokumenti u pošti kao poveznice

Poruka nosi dokument ili datoteku iz Ponistre kao poveznicu umjesto privitka, a svaki primatelj otvara ga pod svojom adresom, u stanju u kojem je kad ga otvori.

## Kako se koristi

### Dodavanje u poruku

1. U obrascu poruke pritisnite {t:mail.attach}, zatim {t:chat.fromDocuments}
2. Odaberite dokument ili datoteku. Popis nudi samo ono čiji ste vlasnik.
3. Stavka se pojavljuje pod {t:mail.shared} poruke. Uz nju odaberite {t:access.role.read} ili {t:access.role.edit}.
4. Isključite kvačicu {t:outside.download} ako stavka smije ostati samo u pregledniku primatelja.
5. Stavku uklanjate pomoću {t:mail.removeFile}.
6. Pošaljite poruku kao i inače.

### Prevelika poruka

1. Ako odlazni poslužitelj odbije poruku jer je prevelika, piše {t:error.mail_too_large}
2. Pritisnite {t:mail.filesAsLinks}. Priložene datoteke spremaju se u vaše Dokumente i prelaze među poveznice.
3. Pošaljite poruku ponovno.

### Otvaranje kod primatelja izvana

1. Primatelj otvara poveznicu iz poruke u pregledniku.
2. Upisuje {t:outside.address} na koju je poruka stigla i pritišće {t:outside.sendCode}.
3. Stranica javlja da kôd čeka na toj adresi, ako je poveznica onamo poslana. Pomoću {t:outside.otherAddress} upisuje drugu.
4. Upisuje {t:outside.code} iz poruke i pritišće {t:outside.open}.

## Kako radi

Poveznice se izrađuju tek kad poruka ode, a stoje na kraju vašeg teksta s naslovom svake stavke. Ako poruka ne ode, sve što je dala poništava se. Poruka [poslana kasnije](help:mail/later) dijeli stavke tek u trenutku slanja, a provjerava ih već kad je zakažete.

Primatelji koji su korisnici instalacije (u bilo kojem od polja primatelja) dobivaju stavku izravno, s odabranom ulogom, kao da ste je s njima podijelili; jaču ulogu koju već imaju zadržavaju. Poveznicu otvaraju prijavljeni, pod svojim imenom.

Za primatelje izvana svaka stavka dobiva jednu poveznicu, vrste {t:outside.kind.people}, koja pušta samo njihove adrese. Kôd ima 6 znamenki, odlazi s vašeg računa pošte (SMTP) i vrijedi 15 minuta, a na istu adresu novi stiže najviše jednom u minuti. Stranica odgovara isto za svaku adresu, pa se iz nje ne može saznati kome je poruka poslana. Tko upiše točan kôd, u tom pregledniku ostaje prijavljen pod svojom adresom najdulje 30 dana i vidi stavku kao [osoba izvana](help:documents/outside-people), s ulogom i preuzimanjem koje ste odabrali.

Pružatelj pošte obično sprema svaku poruku poslanu kroz njegov poslužitelj, pa poruke s kodovima mogu stajati i u vašoj mapi poslane pošte.

Poveznica se vidi u [dijeljenju](help:documents/sharing) stavke, uz adrese primatelja. Ondje je ukidate, a s njom i pristup svih primatelja izvana. U dnevniku pristupa svako otvaranje stoji pod adresom primatelja.

## Ograničenja

- Poruka nosi najviše 20 stavki kao poveznice; inače piše {t:error.invalid_shared}
- Poveznicu izvan instalacije smijete izraditi samo ako vam to dopušta politika instalacije: {t:error.links_not_allowed} Poruka samo kolegama ide i tada.
- Ne nudi se stavka u mapi bez preuzimanja, mapa ni spremljena poveznica na web.
- Pogrešan ili istekao kôd javlja {t:error.wrong_code} Nakon 5 pogrešnih pokušaja: {t:error.too_many_code_tries}
- Korisnik instalacije bez prava na stavku dobiva {t:error.signed_in_inside}
- Bez vašeg računa pošte koji šalje (ActiveSync ne šalje) kodovi ne odlaze.

## Povezano

- [Pisanje poruke](help:mail/composing)
- [Dijeljenje s osobom izvana](help:documents/outside-people)
- [Poveznica izvan instalacije](help:documents/outside)
- [Dijeljenje](help:documents/sharing)
