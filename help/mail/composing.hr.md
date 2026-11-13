# Pisanje poruke

Novu poruku, odgovor ili prosljeđivanje pišete u istom obrascu, koji sam čuva nedovršeno.

## Kako se koristi

![Obrazac za pisanje poruke](shot:mail-compose)

### Nova poruka

1. U Pošti pritisnite {t:mail.compose}.
2. Pod {t:mail.sender} provjerite račun s kojeg šaljete.
3. Pod {t:mail.to} upišite ime ili adresu i odaberite prijedlog. Primatelja uklanjate pomoću {t:mail.removeRecipient}.
4. Za dodatne primatelje pritisnite {t:mail.copies} pa ih upišite pod {t:mail.cc} ili {t:mail.bcc}.
5. Upišite {t:mail.subject} i {t:mail.text}.
6. Pritisnite {t:mail.send}. Dok traje, gumb prikazuje: {t:mail.sending}
7. Da poruka ode u određeno vrijeme, umjesto toga pritisnite {t:mail.later} ([Slanje kasnije](help:mail/later)).
8. Želite li da vas Ponistra podsjeti ako nitko ne odgovori, prije slanja pritisnite ikonu pješčanog sata ([Čekanje odgovora](help:mail/awaiting)).

### Oblikovanje

1. Traka {t:mail.formatting} iznad teksta nudi {t:mail.font}, {t:mail.size}, {t:mail.spacing}, poveznice i slike.
2. Sliku možete staviti u tekst s trake.

### Privitci

1. Pritisnite {t:mail.attach}, zatim {t:chat.fromComputer} i odaberite datoteke.
2. Dokument ili datoteku iz Ponistre šaljete kao poveznicu pomoću {t:mail.attach} i {t:chat.fromDocuments} kako opisuje [Dokumenti u pošti kao poveznice](help:mail/shared-links).
3. Papir snimljen mobitelom prilažete kao PDF pomoću {t:mail.scan}, kako opisuje [Skeniranje](help:pdf/scan).
4. Privitak uklanjate pomoću {t:mail.removeFile}.

### Odgovor i prosljeđivanje

1. U otvorenoj poruci pritisnite {t:mail.reply}, {t:mail.replyAll} ili {t:mail.forward}.
2. Izvorna poruka skrivena je ispod vašeg teksta. Prikazuje se pomoću {t:mail.showQuoted} ili {t:mail.showForwarded}.

### Nedovršena poruka

1. Zatvorite obrazac. Poruka ostaje spremljena.
2. Otvorite {t:mail.role.drafts}. Na vrhu mape nalazi se {t:mail.unsentTitle}.
3. Pritisnite je i nastavite pisati, ili u obrascu pritisnite {t:mail.discard} pa potvrdite ({t:mail.discardTitle}).

## Kako radi

Što pišete sprema se samo od sebe nakon kratke stanke, a obrazac tada prikazuje {t:mail.unsentKept}. Nedovršena poruka čuva se u Ponistri i dostupna je na svakom vašem uređaju, ali ne ulazi u mapu skica kod pružatelja.

Nova poruka polazi s računa koji ste označili kao zadani. Čim upišete prvog primatelja, račun se sam mijenja u onaj s kojeg ste tom primatelju zadnji put pisali ili na koji vam je on pisao, dok sami ne odaberete drugi. Odgovor polazi s računa na koji je poruka stigla. Promjenom računa mijenja se i potpis u tekstu.

Prijedlozi primatelja dolaze iz vaše pošte, kontakata, kolega u instalaciji i imenika poslužitelja. Ako imenik ne odgovara, prijedlozi su samo iz pošte, što piše i ispod polja. Ako imenik za primatelja ima samo interno ime, a ne adresu, obrazac to javlja i traži da upišete adresu. Citirani tekst stoji ispod vašeg teksta i potpisa.

Poruka se šalje kroz poslužitelj računa. Poveznica u poruci iz aplikacije ili druge stranice (`mailto:`) otvara ovaj obrazac s popunjenim poljima.

Kad imate ključ pošte u sefu, uz {t:mail.send} stoje {t:mail.sealing.sign} i {t:mail.sealing.encrypt}. Odgovor na šifriranu poruku šifrira se sam, dok to ne isključite. Više u [Šifrirana pošta](help:mail/encrypted).

Bez mreže, na uređaju označenom za rad bez mreže, ono što pišete sprema se na uređaj, a obrazac prikazuje {t:mail.keptOnDevice}. Poslana poruka čeka mrežu pod {t:mail.laterTitle} ([Rad bez mreže](help:account/offline)).

## Ograničenja

- {t:mail.imageUnsupported}
- {t:mail.linkInvalid}
- Ako poslužitelj odbije neke primatelje, prikazuje se {t:mail.sentRefused} s njihovim adresama. Ostali su poruku primili; pošaljite je odbijenima ponovno nakon ispravka.
- {t:mail.sentUnkept} znači da je poruka otišla, ali se u mapi poslane pošte ne nalazi vaša kopija.
- Odbačena poruka ne može se vratiti.

## Povezano

- [Dokumenti u pošti kao poveznice](help:mail/shared-links)
- [Slanje kasnije](help:mail/later)
- [Čekanje odgovora](help:mail/awaiting)
- [Potpis](help:mail/signature)
- [Računi e-pošte](help:mail/accounts)
- [Skice odgovora](help:mail/drafts)
- [Šifrirana i potpisana pošta](help:mail/encrypted)
- [Rad bez mreže](help:account/offline)
