# Android aplikacija

Na telefonu s Androidom Ponistra radi kao zasebna aplikacija, koja drži vaše kontakte i kalendare u telefonu i sama se ažurira s instalacije.

## Kako se koristi

### Povezivanje s računala

1. U Postavkama otvorite {t:appPasswords.title} i pod {t:phoneApp.title} pritisnite {t:phoneApp.connect}.
2. Na zaslonu se pojavljuje {t:phoneApp.qr}. Skenirajte ga kamerom telefona s Androidom.
3. Na telefonu pritisnite {t:phoneApp.download} ako aplikaciju još nemate i instalirajte je, a zatim {t:phoneApp.open}.
4. Aplikacija traži dopuštenje za kontakte, kalendar i obavijesti te se otvara. Na računalu piše {t:phoneApp.connected} i naziv telefona.

### Povezivanje na samom telefonu

1. Na telefonu otvorite Ponistru u pregledniku pa u Postavkama {t:appPasswords.title} pritisnite {t:phoneApp.connect}.
2. Pritisnite {t:phoneApp.download} ako aplikaciju još nemate, a zatim {t:phoneApp.open}.

## Kako radi

Aplikacija otvara Ponistru u Chromeu kao vlastitu aplikaciju i uz to radi ono što web stranica ne može. Vaši kontakti stoje u imeniku telefona, a vaši kalendari u kalendaru telefona; promjena s telefona ide u Ponistru i obratno, a kalendari organizacije na telefonu se samo čitaju. Kad se isti kontakt ili događaj u međuvremenu promijenio na obje strane, vrijedi promjena iz Ponistre.

Telefon se prijavljuje lozinkom aplikacije koju je dobio pri povezivanju; ona stoji među vašim [lozinkama aplikacija](help:account/app-passwords), gdje je možete i ukloniti. Ako dijalog zatvorite prije nego što se telefon povezao, lozinka koja je čekala na njega uklanja se. Aplikacija dijeli sadržaj u Ponistru, kako opisuje [dijeljenje s Ponistrom](help:phone/share).

Novu verziju aplikacija sama preuzima s instalacije kad se otvori, nakon usklađivanja i dvaput dnevno. Gdje Android to dopušta, instalira je bez pitanja; inače čeka u obavijesti koju dodirnete.

Administrator instalacije u njezinu dnevniku vidi kada je telefon uparen i kada je odjavljen.

## Ograničenja

- Aplikacija postoji samo za Android; kod skeniran drugim telefonom ne povezuje ga.
- Kod za povezivanje vrijedi deset minuta i samo jednom.
- Prije povezivanja Ponistra može zatražiti da [potvrdite da ste to vi](help:account/confirm).
- {t:phoneApp.connect} postoji samo kad instalacija nudi aplikaciju.

## Povezano

- [Dijeljenje s Ponistrom](help:phone/share)
- [Lozinke aplikacija](help:account/app-passwords)
- [Kontakti](help:contacts/overview)
