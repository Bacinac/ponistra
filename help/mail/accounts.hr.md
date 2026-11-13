# Računi e-pošte

Ponistru povezujete s postojećim sandučićima kod bilo kojeg pružatelja, a svaki račun zadržava svoje postavke.

## Kako se koristi

### Povezivanje računa

1. U Pošti ili u Postavkama pod {t:mail.accounts} pritisnite {t:mail.connect}.
2. Ako je administrator to postavio, pritisnite {t:mail.oauth.google} ili {t:mail.oauth.microsoft} i prijavite se kod pružatelja.
3. Inače, pod {t:mail.oauthOr} upišite {t:mail.address} i {t:mail.password}. Neki pružatelji traže {t:mail.appPassword}; poveznica {t:mail.appPasswordMake} vodi na njihovu stranicu.
4. Upišite {t:mail.name}.
5. Pritisnite {t:mail.connect}. Dok traje, gumb prikazuje: {t:mail.checking}

### Postavke poslužitelja

1. Ako Ponistra ne pronađe poslužitelje sama, otvorite {t:mail.servers}.
2. Odaberite {t:mail.protocol}: {t:mail.protocol.imap} ili {t:mail.protocol.activesync}.
3. Upišite {t:mail.username}.
4. Za {t:mail.imap} i {t:mail.smtp} upišite {t:mail.host}, {t:mail.port} i {t:mail.security}: {t:mail.security.tls}, {t:mail.security.starttls} ili {t:mail.security.none}. Za ActiveSync upišite {t:mail.activesync}.

### Izbornik računa

Dugo pritisnite naziv računa u lijevom stupcu Pošte ili ga pritisnite desnom tipkom miša, zatim odaberite:

- {t:tree.rename}: naziv računa koji vidite samo vi.
- {t:mail.edit}: adresa, lozinka i poslužitelji. Ako lozinku ostavite praznu, ostaje dosadašnja.
- {t:mail.signature}: [potpis računa](help:mail/signature).
- {t:mail.color}: {t:mail.color.petrol}, {t:mail.color.green}, {t:mail.color.orange}, {t:mail.color.violet}, {t:mail.color.rose}, {t:mail.color.gold} ili {t:mail.color.blue}.
- {t:mail.default}: račun s kojeg polazi nova poruka.
- {t:mail.together}: poruke računa prikazuju se u zajedničkim mapama. Isti prekidač je kružić uz naziv računa.
- {t:mail.remove}: uklanja račun nakon potvrde ({t:mail.removeTitle}).

## Kako radi

Ponistra preuzima poštu iz sandučića i šalje kroz njega. Ono što je kod pružatelja ne mijenja, osim što pri slanju dodaje kopiju u poslanu poštu. Lozinka se čuva šifrirana. Pri prijavi preko pružatelja Ponistra ne čuva lozinku računa.

Račun s lozinkom možete prebaciti na prijavu preko pružatelja pomoću {t:mail.oauthSwitch.google} ili {t:mail.oauthSwitch.microsoft}. Kad pružatelj prestane prihvaćati prijavu, uz račun se pojavljuje crvena ikona. Pritiskom na nju vidi se greška, a u {t:mail.edit} je ponovna prijava: {t:mail.oauthAgain.google} ili {t:mail.oauthAgain.microsoft}.

Kad pružatelj i dalje daje prijavu, a dolazni poslužitelj računa je odbije ili ne odgovara, ikona ostaje uz račun, a Ponistra pokušava ponovno, prvo nakon minute, zatim u sve duljim razmacima do pola sata. Račun se oporavi sam čim ga poslužitelj prihvati. Poruku koju odlazni poslužitelj tako odbije Ponistra jednom ponovno šalje s novom prijavom.

Nakon uklanjanja računa nova pošta više ne stiže, a preuzete poruke ostaju u posebnoj skupini mapa u lijevom stupcu.

Boje čine račune prepoznatljivima u popisu poruka i u obrascu za pisanje.

## Ograničenja

- Prijava preko Googlea i Microsofta nudi se samo kad je administrator postavi.
- Microsoft za neke adrese ne prima lozinku, nego samo prijavu preko Microsofta, pa bez te prijave takav račun nije moguće povezati.
- Outlook.com pušta aplikacije do pošte samo kad je IMAP dopušten u njegovim postavkama (Postavke → Pošta → Prosljeđivanje i IMAP); u Microsoftu 365 i Google Workspaceu administrator može isključiti IMAP za sandučić.
- Neki pružatelji za poštu ne primaju lozinku računa, nego lozinku aplikacije, uz uključenu potvrdu u dva koraka.
- Brisanje i premještanje u Ponistri ne prenose se pružatelju.

## Povezano

- [Pregled pošte](help:mail/overview)
- [Potpis](help:mail/signature)
