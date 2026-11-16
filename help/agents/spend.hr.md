# Potrošnja tokena

Koliko su tokena potrošili razgovori radnog prostora, po projektu, modelu, krugu, razgovoru i danu, uz limite pretplate i trošak AI-ja same Ponistre.

## Kako se koristi

1. Na stranici {t:rail.projects} pritisnite {t:workspace.view.spend}, skroz desno u retku s {t:workspace.view.chat} (na telefonu s {t:workspace.view.overview}).
2. Na vrhu stoji zadnji mjesec: {t:workspace.spend.input}, {t:workspace.spend.output}, {t:workspace.spend.cacheRead} i {t:workspace.spend.cacheWrite} u tokenima, {t:workspace.spend.worth} i {t:workspace.spend.api}.
3. Ispod su isti stupci {t:workspace.spend.projects} (stupac {t:workspace.spend.project}), {t:workspace.spend.models} ({t:workspace.spend.model}), {t:workspace.spend.rounds} ({t:workspace.spend.round}) i {t:workspace.spend.chats} ({t:workspace.spend.chat}), svaki redak sa stupcem {t:workspace.spend.week}. Ako zadržite pokazivač na razgovoru, piše njegova oznaka sesije.
4. Pod {t:workspace.hours.days} za svaki dan stoji {t:workspace.spend.turns}, {t:workspace.spend.worth}, {t:workspace.spend.session} i {t:workspace.limits.week} kako su izmjereni toga dana, te {t:workspace.spend.api}.
5. Na dnu, pod {t:workspace.spend.actions}, stoji svaka radnja Ponistre koja je u mjesecu koristila AI, s brojem izvođenja i troškom.
6. Za drugi mjesec odaberite ga u polju {t:workspace.hours.month}.

Dok ništa nije izmjereno, stoji {t:workspace.spend.none}

## Kako radi

Tokene broji radni prostor iz istih zapisa razgovora iz kojih mjeri [vrijeme rada](help:agents/projects), svake minute: za svaki odgovor modela koliko je pročitao kao novi ulaz, koliko je napisao, koliko je pročitao iz cachea i koliko je u njega upisao. Jedan odgovor Claude Code zapisuje u više redaka s istim brojevima, pa se svaki broji jednom; i odgovor koji je zapis presjekao napola broji se jednom. Pomoćni agenti koje je razgovor pokrenuo broje se pod tim razgovorom. Razgovor koji je u krugu broji se i pod tim krugom, od trenutka kad je u njemu. Ponistra tokene drži u svojoj bazi po satu i modelu, s oznakom dokle je koji zapis pročitan, pa ponovno čitanje ništa ne broji dvaput, a izbrojeno ostaje i kad se zapis razgovora obriše. Prvi put radni prostor pročita sve zapise koje još ima od početka, pa potrošnja stoji i za razgovore od prije.

Pretplata se ne plaća po tokenu, pa {t:workspace.spend.worth} kaže koliko bi isti tokeni stajali po cijenama API-ja u dolarima: upis u cache po 1,25 cijene ulaza, čitanje iz cachea po njegovoj cijeni. Ta težina otprilike prati kako ih broje limiti pretplate, pa je mjerilo za usporedbu, a ne račun. Modeli za koje Ponistra nema cijenu ne ulaze u iznos; iznos tada nosi zvjezdicu, a ispod mjeseca piše koji su to modeli. {t:workspace.spend.week} dijeli iznos retka s onim što je od početka tekućeg tjednog prozora potrošeno i kaže koliki je to otprilike dio tjednog limita.

Limite radni prostor javlja Ponistri pri svakoj promjeni petosatnog ili tjednog prozora, a Ponistra svako mjerenje čuva; za dan stoji najviši izmjereni petosatni prozor i zadnje izmjereni tjedni. {t:workspace.spend.api} i {t:workspace.spend.actions} su ono što je Ponistra sama platila svojim ključem za AI, iz troška svake radnje. Razgovora stoji najviše 50, onih s najvećim iznosom. Stranica se osvježi sama kad stignu novi tokeni ili novo mjerenje.

## Ograničenja

Stranicu vidi samo vlasnik radnog prostora ({t:error.not_the_owner}). Broje se samo razgovori čiji su zapisi u radnom prostoru, u njemu i u uređivaču; razgovori iste pretplate na drugim računalima troše limite, ali ovdje ne stoje. Tokeni razgovora čiji je zapis obrisan prije nego što ga je radni prostor pročitao nisu izbrojeni. Dani su po hrvatskom vremenu.

## Povezano

- [Projekti](help:agents/projects)
- [Upis vremena rada](help:agents/hours)
