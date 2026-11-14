# Upis vremena rada

Izmjereno vrijeme rada na projektima radnog prostora Ponistra upisuje u Clockify ili u TaskStreamerove timesheetove i briše transkripte arhiviranih razgovora kad više ne trebaju.

## Kako se koristi

### Odredište

1. Na stranici {t:rail.projects} otvorite {t:workspace.view.hours} i pritisnite {t:workspace.hours.settings}
2. Pod {t:workspace.sheets.heading}, kod {t:workspace.sheets.clockify} ili {t:workspace.sheets.taskstreamer}, pritisnite {t:workspace.sheets.setUp}
3. Upišite {t:workspace.sheets.key}; za TaskStreamer još {t:workspace.sheets.address} i {t:workspace.sheets.person}.
4. Ostavite ili promijenite {t:workspace.sheets.label} (zadano {t:workspace.sheets.labelDefault}) i {t:workspace.sheets.since}, pa pritisnite {t:tree.save}.
5. Pritisnite {t:workspace.sheets.edit} i pod {t:workspace.sheets.projects} za svaki naš {t:workspace.sheets.project} odaberite u stupcu {t:workspace.sheets.target} projekt odredišta, ili ga ostavite na {t:workspace.sheets.notWritten}. Projekt koji se nikad ne upisuje označite kao {t:workspace.sheets.excluded}. Kad u Clockifyju dodate projekt, pritisnite {t:workspace.sheets.refresh}.
6. Uključite {t:workspace.sheets.nightly} kad upis treba ići sam; dok je isključeno, upisuje se samo kad pritisnete {t:workspace.sheets.write}.

### Upis i usporedba

1. Na kartici odredišta stoji {t:workspace.sheets.mode} ({t:workspace.sheets.nightly} ili {t:workspace.sheets.byHand}), {t:workspace.sheets.since}, {t:workspace.sheets.due} i {t:workspace.sheets.writtenAt}.
2. {t:workspace.sheets.write} odmah upisuje svaki dan koji čeka; nakon toga stoji {t:workspace.sheets.wrote}.
3. {t:workspace.sheets.compare} otvara mjesec po danima: za svaki projekt odredišta {t:workspace.sheets.measured}, {t:workspace.sheets.own} (unosi s opisom unosa) i {t:workspace.sheets.others} (ostali unosi na istom projektu), uz stanje dana: {t:workspace.sheets.state.same}, {t:workspace.sheets.state.differs}, {t:workspace.sheets.state.open} ili {t:workspace.sheets.state.before}. Mjesec se mijenja u polju {t:workspace.hours.month}.
4. {t:workspace.sheets.remove} uz potvrdu {t:workspace.sheets.removeHeading} prestaje upisivati u to odredište.

### Transkripti arhiviranih razgovora

1. U istim postavkama, pod {t:workspace.removal.heading}, u polju {t:workspace.removal.label} odaberite {t:workspace.removal.never}, {t:workspace.removal.now} ili {t:workspace.removal.after}.
2. Za {t:workspace.removal.after} upišite {t:workspace.removal.days}; zadano je 30.

## Kako radi

Upisuje se vrijeme koje pokazuje [Projekti](help:agents/projects) pod {t:workspace.view.hours}: blokovi rada po projektu, dan po hrvatskom vremenu. Naši projekti upisani u isti projekt odredišta spajaju se u iste blokove, a ne zbrajaju. Dan se upisuje tek kad je prošao i nijedan njegov blok više ne može rasti, dakle najranije 17 minuta nakon zadnjeg rada; dan prije datuma {t:workspace.sheets.since} nikad. Upisani dan pamti se u Ponistri. Promijeni li se kasnije ono što je izmjereno, na primjer kad radni prostor dočita zaostale transkripte, dan se upisuje ponovno; inače se odredište više ne pita ništa.

Clockify za svaki projekt i dan dobiva jedan unos koji počinje s prvim blokom i traje koliko svi blokovi zajedno. Opis unosa je {t:workspace.sheets.label} i iza njega naši projekti. Unosi s tim opisom na projektima koji se upisuju smatraju se upisanima iz Ponistre: isti unos ostaje, drukčiji se briše i upisuje nov. Ručne unose i projekte koji se ne upisuju Ponistra ne dira. Clockifyjev besplatni ključ prima 30 zahtjeva na sat; Ponistra ih troši najviše 28, a ostatak čeka sljedeći prolaz. TaskStreamer dobiva svaki blok kao zaseban unos u timesheetu korisnika iz polja {t:workspace.sheets.person}. Na danima koji se upisuju zamjenjuju se samo unosi koje je upisao alat, a dani čiji timesheet više nije u nacrtu preskaču se. Ključ se u bazi čuva zapečaćen i nikad se ne prikazuje; polje ostaje {t:workspace.sheets.keyKept} dok ne upišete novi.

S uključenim {t:workspace.sheets.nightly} Ponistra svakih 15 minuta upisuje dane koji su u međuvremenu završili ili se promijenili, pa je prethodni dan upisan nekoliko minuta iza ponoći.

Transkript arhiviranog razgovora, zajedno s mapom koju razgovor drži uz njega, radni prostor briše tek kad Ponistra potvrdi da je vrijeme iz njega pročitala do zadnjeg retka. Nikad ne briše razgovor koji radi ni razgovor u krugu koji nije zatvoren. Razgovor koji nije na popisu arhiviranih smatra se arhiviranim od zadnje promjene svog transkripta, a briše se najranije sat vremena nakon nje. Izmjereno vrijeme ostaje u Ponistri i nakon brisanja, ali se takav razgovor više ne može nastaviti.

## Ograničenja

Postavke postoje samo za vlasnika radnog prostora za kod. TaskStreamer mora primati upis vremena kroz API ključ; dok ga ne prima, kartica javlja {t:error.sheet_missing} {t:error.sheet_refused} znači da ključ ne vrijedi, pa upišite novi. {t:error.sheet_busy} znači da je potrošen Clockifyjev sat i da se upis nastavlja sam. {t:error.sheet_unreachable} i {t:error.sheet_failed} ostavljaju dane da čekaju sljedeći pokušaj. Odredište svake vrste postoji samo jedno.

## Povezano

- [Projekti](help:agents/projects)
