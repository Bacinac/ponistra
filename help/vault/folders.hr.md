# Mape i premještanje u sefu

Mape slažu stavke unutar zbirke, a premještanjem stavku stavljate u drugu mapu ili u drugu zbirku.

## Kako se koristi

### Mape

1. U otvorenoj zbirci u izborniku ostalih radnji odaberite {t:create.folder}, upišite naziv i pritisnite {t:tree.create}. Nova mapa nastaje u mapi koja je otvorena.
2. Otvorite mapu u lijevom stupcu, ispod zbirke.
3. Za otvorenu mapu u izborniku ostalih radnji odaberite {t:vault.renameFolder} ili {t:vault.deleteFolder}.
4. Brisanje potvrdite u dijalogu {t:vault.deleteFolderTitle}

### Premještanje stavke

1. U otvorenoj stavci u izborniku radnji odaberite {t:tree.move}.
2. Pod {t:vault.moveTo} odaberite zbirku ili mapu u njoj.
3. Pritisnite {t:tree.moveHere}.

### Više stavki odjednom

1. Dugo pritisnite stavku u popisu. Nakon toga pritisak na drugu stavku dodaje je u odabir ili je iz njega uklanja, a uz {k:Shift} cijeli raspon.
2. {k:Mod-a} odabire sve stavke u popisu, a {k:Escape} poništava odabir.
3. Iznad popisa pritisnite {t:tree.move} ili {t:tree.toTrash}. Iste radnje nudi desni klik na stavku.

## Kako radi

Nazivi mapa šifriraju se kao i stavke. Mapa može sadržavati druge mape. Obrisana mapa nestaje zajedno s mapama u njoj, a njezine stavke ostaju u zbirci, izvan mapa.

Stavka premještena u drugu zbirku postaje vidljiva članovima te zbirke i nestaje iz dosadašnje. Ključ stavke pritom se u pregledniku zaključava ključem nove zbirke.

## Ograničenja

- Mape i premještanje traže pravo uređivanja u zbirci, a premještanje u drugu zbirku i u njoj.
- Kad je upisana pretraga, popis prikazuje stavke iz svih mapa, uz put do njihove mape, a mape se ne prikazuju.

## Povezano

- [Razvrstavanje u mape](help:vault/sorting)
- [Stavke sefa](help:vault/items)
- [Smeće sefa](help:vault/trash)
