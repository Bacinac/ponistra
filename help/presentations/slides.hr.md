# Slajdovi

Svaki dokument može se prikazati kao prezentacija: naslovi dijele tekst kartice na slajdove, a raspored slajda određuje gdje stoji koji dio teksta.

## Kako se koristi

### Prikaz slajdova

1. Desno na traci alata odaberite {t:view.label} pa {t:view.slides}.
2. Pišite kao u tekstu. Novi slajd počinje svakim {t:command.title}, svakim {t:command.heading1} i svakim {t:command.slideBreak} iz izbornika {t:editor.insert}.
3. Prazna mjesta rasporeda podsjećaju što se u njih upisuje, na primjer naslov ili tekst.

### Raspored i veličina

1. Stanite u slajd i na traci alata, pod {t:commandGroup.slideLayout}, odaberite {t:slides.layout.auto}, {t:slides.layout.title}, {t:slides.layout.content}, {t:slides.layout.section}, {t:slides.layout.two}, {t:slides.layout.titleOnly} ili {t:slides.layout.blank}.
2. Pod {t:commandGroup.slideSize} odaberite {t:command.slideSize.wide} ili {t:command.slideSize.standard}.
3. {t:command.hideSlide} skriva slajd iz izlaganja. Iznad skrivenog slajda piše {t:slides.hidden}.

### Bilješke govornika

1. U izborniku {t:editor.insert} odaberite {t:command.speakerNotes}. Bilješke se otvaraju na kraju slajda u kojem ste.
2. {k:Enter} u praznom retku bilješki vraća u slajd.

## Kako radi

{t:slides.layout.auto} bira raspored prema sadržaju slajda: slajd koji počinje naslovom dokumenta je {t:slides.layout.title}, slajd s {t:command.columnBreak} je {t:slides.layout.two}, a slajd koji počinje naslovom razine 1 je {t:slides.layout.content} kad ispod naslova ima teksta, a inače {t:slides.layout.section}. Tekst prije prvog naslova je zaseban slajd kad nije prazan.

Kad promijenite raspored, tekst se ne gubi: dio za koji novi raspored nema mjesta ide tamo gdje bi ga stavio ugrađeni raspored iste vrste. Prezentacija učitana iz PowerPointa zadržava svoj predložak, pa se rasporedi nude pod nazivima iz predloška. Slajd kojem je PowerPoint dao vlastitu pozadinu prikazuje nju umjesto pozadine rasporeda i zadržava je kad se dokument spremi kao PowerPoint.

Slajdovi se broje kroz sve kartice dokumenta.

## Ograničenja

- Raspored, veličinu i skrivanje mijenja samo onaj tko smije uređivati dokument.
- Bilješke govornika ne mogu se dodati iz tablice, zaglavlja, podnožja ni bilješke.

## Povezano

- [Izlaganje](help:presentations/show)
- [Uređivač dokumenta](help:text/overview)
- [Spremanje u datoteku](help:text/export)
