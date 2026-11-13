# Rad sa stavkama

Stavke u mapi otvarate, preimenujete, kopirate, premještate i bacate u smeće, jednu po jednu ili više odjednom.

## Kako se koristi

### Radnje nad jednom stavkom

1. Desnom tipkom miša pritisnite stavku u popisu ili pritisnite gumb s tri točke na kraju njezina retka. Mapa u stablu lijevog stupca nudi {t:tree.rename} i {t:tree.toTrash} na desni klik ili dugi pritisak.
2. Odaberite {t:tree.open}, {t:tree.rename}, {t:tree.move} ili {t:tree.toTrash}.
3. Za dokument odaberite {t:copy.make}. Upišite naziv kopije i pritisnite {t:tree.create}.
4. Za datoteku odaberite {t:file.download}.
5. Pomoću {t:access.share} otvara se ploča s pravima stavke.

### Odabir više stavki

1. Dugo pritisnite stavku ili je pritisnite uz {k:Mod}. Na računalu možete stati na redak i pritisnuti {k:Space}.
2. Nakon toga dodir ili klik dodaje stavku u odabir ili je iz njega uklanja. Držite {k:Shift} za raspon. Dvostruki pritisak i tada otvara stavku.
3. Pritisnite {k:Mod-a} ili kvačicu na traci odabira za sve stavke u mapi. U izborniku trake su {t:explorer.selectAll}, {t:explorer.invert} i {t:explorer.clear}.
4. Na traci odabira odaberite {t:tree.move} ili {t:tree.toTrash}. Ostale radnje su pod tri točke.
5. Pritisnite {k:Escape} za odustajanje od odabira, a {k:Delete} za premještanje odabranog u smeće.

### Premještanje

1. Odaberite {t:tree.move}. Otvara se okvir {t:tree.moveTitle}.
2. Na vrhu okvira odaberite {t:tree.root}, {t:tree.company} ili {t:tree.shared}, pa uđite u mapu pritiskom na nju.
3. Pritisnite {t:tree.moveHere} ili {t:tree.cancel}.
4. Stavku možete i povući mišem na mapu u popisu, na mapu u lijevom stupcu, na korak putanje ili na {t:trash.title}.

## Kako radi

Kopija dokumenta nastaje uz izvornik, a naziv joj počinje s „Kopija –”. Ako u mapu izvornika ne smijete dodavati, kopija nastaje u {t:tree.root}. Dok dugotrajna izrada kopije traje, u donjem desnom kutu piše {t:job.copy}.

Stavka premještena u mapu preuzima prava te mape, a prava koja je imala sama zadržava. Premještanje i brisanje vide svi koji imaju pristup, odmah. Kad više stavki povučete odjednom, premještaju se sve odabrane. Datoteku povučenu iz popisa na radnu površinu preglednik sprema kao datoteku.

Stavka u smeću ne briše se odmah: vraća se iz [smeća](help:documents/trash). Okvir premještanja ne nudi mapu koju premještate. Kad mapa nema podmapa, piše: {t:tree.noSubfolders}

## Ograničenja

- Preimenovanje, premještanje i bacanje u smeće traže pravo uređivanja. Mape tvrtke uređuje samo administrator.
- U {t:tree.root} možete premjestiti samo stavke kojima ste vlasnik.
- Iz mape {t:confined.label} stavka se ne može premjestiti van, preuzeti ni kopirati izvan mape. Radnja je tada onemogućena uz napomenu {t:confined.hint}.
- {t:copy.make} postoji samo za dokumente, ne za mape i datoteke.
- Bez mreže preimenovanje, premještanje i bacanje u smeće su onemogućeni ([Rad bez mreže](help:account/offline)).

## Povezano

- [Pregled dokumenata](help:documents/overview)
- [Smeće](help:documents/trash)
- [Dijeljenje](help:documents/sharing)
