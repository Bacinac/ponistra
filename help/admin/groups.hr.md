# Grupe

Grupe okupljaju korisnike kojima se zajedno daju mape tvrtke, zbirke sefa i dijeljene stavke.

## Kako se koristi

1. Na stranici {t:users.title} pritisnite {t:users.newGroup}, upišite naziv i pritisnite {t:tree.create}.
2. Korisnike u grupu dodajete u njihovu računu, pod {t:users.edit}, kvačicom uz naziv grupe.
3. U odjeljku {t:access.groups} uz grupu otvorite izbornik i odaberite {t:tree.rename} ili {t:users.deleteGroup}.
4. Brisanje potvrdite u dijalogu {t:users.deleteGroupTitle}

## Kako radi

Uz svaku grupu piše koliko ima članova ({t:users.members}). Kad obrišete grupu, njezini članovi gube pristup koji im je grupa davala, a njihov vlastiti pristup ostaje.

Dodavanje, preimenovanje i uklanjanje grupe upisuju se u [dnevnik](help:admin/journal).

## Ograničenja

- Dvije grupe ne mogu imati isti naziv.
- Grupa koja dolazi od izdavatelja ili imenika ne može se preimenovati ni obrisati, a članove joj određuje izvor; uz njezin naziv piše naziv izvora. Vidi [Vanjska prijava i imenici](help:admin/sources).
- Grupa se ne može obrisati ako bi neka stavka na vrhu ostala bez vlasnika ili neka zbirka sefa bez vlasnika.
- Dok nema nijedne grupe, piše: {t:users.noGroups}

## Povezano

- [Korisnici](help:admin/users)
- [Mape i zbirke tvrtke](help:admin/company)
