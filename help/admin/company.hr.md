# Mape i zbirke tvrtke

Administrator postavlja mape tvrtke i zbirke sefa tvrtke te ih dodjeljuje grupama.

## Kako se koristi

### Mapa tvrtke

1. Na stranici {t:users.title}, u odjeljku {t:company.title}, pritisnite {t:company.new}.
2. Upišite {t:tree.name}.
3. Pod {t:access.here} za {t:access.everyone} i za svaku grupu odaberite {t:company.noRole}, {t:access.role.read}, {t:access.role.edit} ili {t:access.role.own}.
4. Po potrebi označite {t:confined.label}, pa pritisnite {t:tree.create}.
5. Postojeću mapu mijenjate u izborniku njezina retka s {t:company.edit}, a brišete s {t:company.delete} i potvrdom u dijalogu {t:company.deleteTitle}

### Zbirka sefa tvrtke

1. U odjeljku {t:vault.company.title} pritisnite {t:vault.company.new}.
2. Upišite naziv i grupama dodijelite uloge kao za mapu tvrtke.
3. Zbirku mijenjate s {t:vault.company.edit}, a brišete s {t:vault.company.delete} i potvrdom u dijalogu {t:vault.company.deleteTitle}

## Kako radi

Mapa tvrtke pojavljuje se pod {t:tree.company} korisnicima kojima ste je dodijelili. Vi je postavljate i dodjeljujete, a njezin sadržaj vidi samo tko u njoj ima ulogu. U mapi {t:confined.label} tko nije vlasnik dokumente čita i uređuje samo u Ponistri. Uz mapu u popisu stoji tko ima koju ulogu, a uz mapu bez preuzimanja ikona lokota.

Zbirku sefa tvrtke administrator slaže, ali je ne može pročitati: ključ zbirke izrađuje prvi vlasnik koji je otvori u svojem sefu.

## Ograničenja

- Mapa i zbirka spremaju se tek kad barem jedna grupa ili {t:access.everyone} ima ulogu {t:access.role.own}.
- Obrisati se može samo prazna mapa tvrtke i samo prazna zbirka, a mapa pod zakonskim čuvanjem ne može se obrisati.
- Dok ih nema, piše: {t:company.none} odnosno {t:vault.company.none}

## Povezano

- [Grupe](help:admin/groups)
- [Mapa na poslužitelju](help:admin/file-server)
- [Mape tvrtke](help:documents/company)
