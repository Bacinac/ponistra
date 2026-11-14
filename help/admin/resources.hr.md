# Sobe i resursi

Administrator vodi popis soba, opreme i vozila koje korisnici rezerviraju stavljanjem na događaj.

## Kako se koristi

1. Otvorite {t:admin.title} i odaberite {t:resources.title}.
2. Pritisnite {t:resources.new}.
3. Upišite {t:resources.name}, odaberite {t:resources.kind} ({t:resources.kind.room}, {t:resources.kind.equipment}, {t:resources.kind.vehicle} ili {t:resources.kind.other}) te po želji {t:resources.capacity} i {t:resources.place}.
4. Ostavite označeno {t:resources.active} i pritisnite {t:tree.create}.
5. U retku resursa pritisnite {t:resources.edit} ili {t:resources.delete}; brisanje potvrdite u dijalogu {t:resources.deleteTitle}

## Kako radi

Soba, oprema ili vozilo rezervira se tako da se stavi na događaj, a u isto vrijeme može biti samo na jednom. Resurs bez oznake {t:resources.active} korisnici više ne vide i ne mogu ga staviti na događaj; u vašem popisu stoji uz oznaku {t:resources.retired}.

Obrisan resurs nestaje sa svih događaja na kojima je bio rezerviran.

Dodavanje, promjena i uklanjanje prostorije ili resursa upisuju se u [dnevnik](help:admin/journal).

## Ograničenja

- Dok nema nijednog resursa, piše: {t:resources.none}
- Resurs izvan uporabe ostaje na događajima na kojima je već rezerviran.

## Povezano

- [Sobe i resursi u kalendaru](help:calendar/rooms)
- [Neradni dani](help:admin/workdays)
