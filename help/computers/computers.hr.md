# Računala

Računala s Ponistra OS-om kojima upravljate vode se iz Ponistre: njihove stranice, upozorenja, upravitelji, ključ za oporavak diska i lozinka sigurnosnih kopija.

## Kako se koristi

### Otvaranje računala

1. Na traci modula pritisnite {t:rail.computers}. Na mobitelu je u izborniku računa. Administrator dolazi i kroz {t:admin.title}, {t:computers.title}.
2. U lijevom stupcu su računala kojima upravljate. Uz naziv je oznaka {t:computers.connected} ili {t:computers.offline} i broj upozorenja koja traju.
3. Pritisnite računalo. Ispod naziva su stranice računala, iste kao na njegovoj vlastitoj stranici, i {t:computers.manage}.
4. Dok nijedno računalo ne vodite, stranica piše: {t:computers.none}

### Upravljanje

1. Otvorite računalo i pritisnite {t:computers.manage}.
2. Pod {t:computers.alerts} su upozorenja koja traju, s razinom {t:computers.severity.info}, {t:computers.severity.warning} ili {t:computers.severity.critical} i vremenom kad su nastala.
3. Pod {t:computers.managers} odaberite osobu u polju {t:computers.manager.add} i pritisnite {t:computers.manager.addButton}. Upravitelja uklanjate gumbom {t:computers.manager.remove} uz njegovo ime.
4. Pod {t:computers.secret.recovery_key} i {t:computers.secret.backup_password} piše {t:computers.secret.kept} s vremenom kad ih je računalo predalo. Pritisnite {t:computers.secret.show} i potvrdite da ste to vi.
5. Pod {t:computers.openings} je tko je i kada otvorio koju tajnu i s koje adrese.
6. Pod {t:computers.remove} pritisnite {t:computers.remove.button} i potvrdite.

### Kodovi i računala bez upravitelja

1. Pod {t:computers.codes} su jednokratni kodovi koje ste izradili, a nijedno ih računalo još nije iskoristilo: završetak koda i rok. {t:computers.code.delete} poništava kod.
2. Administrator pod {t:computers.orphaned} vidi računala kojima više nitko ne upravlja i pritiskom na {t:computers.takeOver} postaje njihov upravitelj.

## Kako radi

Računalo je stalno povezano s Ponistrom vezom koju samo otvara, pa mu ne treba javna adresa ni otvoreni port. Stranice računala u Ponistri šalju svaki zahtjev kroz tu vezu, a računalo ga izvodi kao vaš račun, prema vašoj adresi e-pošte, i bilježi ga u svojim zadacima. Ono što smije samo vlastita stranica računala, upis u Ponistru i izlazak iz nje, ovdje se ne nudi. ISO datoteka za gosta najprije se u dijelovima učitava u Ponistru, a Ponistra je zatim šalje računalu.

Dok računalo nije povezano, uz naziv piše {t:computers.offline} i kad je zadnji put bilo na vezi, a njegove stranice ne pokazuju stare podatke nego grešku.

Popis vidi samo upravitelj. Prvi upravitelj je administrator koji je izradio kod kojim se računalo upisalo; svaki upravitelj dodaje druge korisnike instalacije. Računalu uvijek ostaje barem jedan upravitelj, pa se zadnji ne može ukloniti. Kad nijedan upravitelj više nije aktivan, na primjer jer mu je račun obrisan, računalo se pojavljuje administratorima pod {t:computers.orphaned}. Osoba koja nije upravitelj, a vlasnik je gosta na računalu, otvara samo konzolu i datoteke snimki tog gosta; vlasništvo provjerava računalo.

Upozorenje koje nastane, promijeni razinu ili prođe javlja se svim aktivnim upraviteljima [obaviješću](help:account/notifications) koja otvara računalo. Upozorenje razine {t:computers.severity.critical} šalje se s najvećom hitnošću. E-poštom se upozorenja ne šalju.

Ključ za oporavak i lozinku sigurnosnih kopija računalo predaje samo, a Ponistra ih čuva šifrirane. Svako otvaranje traži [potvrdu da ste to vi](help:account/confirm) i bilježi se uz računalo s osobom, vremenom i adresom; popis pokazuje zadnjih 100. Obrisana osoba stoji kao {t:computers.someone}. Otvorena tajna ostaje na zaslonu dok ne napustite stranicu.

Uklanjanje briše računalo iz Ponistre zajedno s ključem i lozinkom i prekida njegovu vezu, a računalo se zatim može ponovno upisati samo novim kodom. Računalo koje je sa svoje stranice izašlo iz Ponistre ostaje na popisu s ključem i lozinkom, ali mu se stranice više ne otvaraju.

Popis i stanje osvježavaju se čim se promijene, bez ponovnog učitavanja stranice.

## Ograničenja

- Nova računala dodaje samo administrator, gumbom {t:computers.add}.
- {t:computers.secret.none} Računalo tajnu predaje nakon instalacije; dok to ne učini, nema što otvoriti.
- {t:computers.error.computer_offline} Računalo je ugašeno ili nema mrežu; pričekajte da se ponovno poveže.
- {t:computers.error.computer_timeout} i {t:computers.error.stream_not_opened} Računalo je zauzeto ili veza puca; pokušajte ponovno.
- {t:computers.error.request_too_large} Zahtjev ne stane u vezu; datoteka ide kroz učitavanje.
- {t:computers.error.forbidden} Niste upravitelj tog računala ni vlasnik gosta.
- {t:computers.error.not_found} Računalo je uklonjeno ili ste prestali biti njegov upravitelj.
- {t:computers.error.last_manager} Najprije dodajte drugog upravitelja.
- {t:computers.error.invalid_user} Upravitelj može biti samo aktivan korisnik instalacije, ne gost ni zajednički sandučić.
- {t:computers.error.not_kept} Računalo tu tajnu još nije predalo.
- {t:computers.error.secret_unreadable} Ključ kojim je tajna šifrirana više ne postoji na instalaciji; javite administratoru.
- {t:computers.error.invalid_upload} Učitavanje datoteke nije dovršeno; učitajte je ponovno.

## Povezano

- [Datoteke gostiju na računalima](help:files/guests)
- [Obavijesti](help:account/notifications)
- [Potvrda da ste to vi](help:account/confirm)
