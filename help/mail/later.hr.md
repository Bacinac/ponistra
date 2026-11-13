# Slanje kasnije

Poruka koju ste napisali čeka u Ponistri i odlazi s vašeg računa u trenutku koji odaberete.

## Kako se koristi

### Odabir vremena

1. Napišite poruku u [obrascu za pisanje](help:mail/composing).
2. Pritisnite {t:mail.later}. Otvara se pitanje {t:mail.laterTitleAsk}
3. Odaberite {t:when.tomorrow} ili {t:when.monday}, ili upišite {t:when.day} i {t:when.time} pa pritisnite {t:mail.later}.

### Poruke koje čekaju

1. U lijevom stupcu Pošte, ispod pristigle pošte, otvorite {t:mail.laterTitle}. Redak je vidljiv samo dok neka poruka čeka; ako nema nijedne, stranica kaže: {t:mail.laterNone}
2. Broj uz redak pokazuje koliko poruka čeka, a crven je kad je neka od njih ostala neposlana.
3. Dugo pritisnite redak ili ga pritisnite desnom tipkom za izbornik: {t:mail.laterEdit}, {t:mail.laterNow}, {t:mail.laterMove} ili {t:mail.discard}.

### Promjena poruke

1. Pritisnite redak ili odaberite {t:mail.laterEdit}. Poruka se otvara u obrascu i prestaje čekati, pa ne može otići dok je mijenjate.
2. Kad završite, ponovno pritisnite {t:mail.later} ili {t:mail.send}. Ako obrazac zatvorite, poruka ostaje pod {t:mail.unsentTitle}.

## Kako radi

Vrijeme čuva poslužitelj, pa poruka odlazi i kad su svi vaši uređaji isključeni. Provjera se obavlja svakih petnaest sekundi, pa poruka može otići toliko kasnije od odabranog trenutka.

Vrijeme upisujete po vremenu na svojem uređaju. Poruka pri slanju dobiva datum trenutka kad je stvarno otišla i završava u poslanoj pošti kao svaka druga. Privitci i slike čuvaju se dok poruka čeka.

Poruka se provjerava već pri zakazivanju, pa se poruku bez primatelja ili s neispravnom adresom ne može zakazati.

Poruka napisana na uređaju bez mreže čeka na vrhu popisa s oznakom {t:mail.queuedWaiting} i odlazi kroz isti red čim se mreža vrati ([Rad bez mreže](help:account/offline)).

## Ograničenja

- Poruka koja nije uspjela ostaje među onima koje čekaju, s razlogom ispod retka, i dobivate [obavijest](help:account/notifications) ako ste je uključili. Ne pokušava se ponovno sama. Kad uklonite uzrok, odaberite {t:mail.laterNow}.
- Ako poslužitelj odbije samo neke primatelje, ostali su poruku primili, poruka je u poslanoj pošti, a obavijest kaže da je neki primatelji nisu dobili.
- {t:error.mail_interrupted}
- {t:error.mail_account_gone} Otvorite poruku, odaberite drugi račun i pošaljite je.
- {t:error.mail_sending} Takva se poruka više ne može promijeniti ni odbaciti.
- Poruka odgovor ili prosljeđivanje ostaje neposlana ako ste izvornu poruku u međuvremenu trajno izbrisali.

## Povezano

- [Pisanje poruke](help:mail/composing)
- [Pregled pošte](help:mail/overview)
- [Rad bez mreže](help:account/offline)
