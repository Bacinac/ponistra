# Tekstne datoteke

Tekstna datoteka, poput zapisa, konfiguracije ili izvornog koda, prikazuje se samo za čitanje, s brojevima redaka, isticanjem sintakse i pretragom.

## Kako se koristi

### Pretraga

1. Otvorite datoteku, pritisnite tekst i zatim {k:Mod-f}. Iznad teksta otvara se polje {t:text.find}.
2. Upišite traženi tekst i pritisnite {k:Enter} za sljedeći pogodak.
3. Gumbi {t:text.next} i {t:text.previous} kreću se po pogocima, a {t:text.all} odabire sve pogotke. Isto rade {k:F3} i {k:Shift-F3}.
4. Uključite {t:text.matchCase}, {t:text.regexp} ili {t:text.byWord} kad trebate točnije traženje.
5. {t:text.close} ili {k:Escape} zatvara pretragu.

### Odlazak na redak

1. Pritisnite {k:Mod-Alt-g}.
2. U polje {t:text.goToLine} upišite broj retka i pritisnite {t:text.go}.

## Kako radi

Boje sintakse odabiru se prema nastavku naziva datoteke, pa se, primjerice, datoteke `.py`, `.js` ili `.json` prikazuju istaknuto. U donjem retku stoji kodna stranica u kojoj je tekst pročitan.

Tekst se može odabrati i kopirati, ali ne i mijenjati.

## Ograničenja

- Prikazuje se najviše prvih 5 MB datoteke. Kad je datoteka veća, donji redak to javlja, a cijela se datoteka dobiva preuzimanjem.
- Datoteka se ne može uređivati u Ponistri.

## Povezano

- [Datoteke](help:files/overview)
