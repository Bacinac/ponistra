# Datoteke na mreži

Stranica {t:locations.title} otvara mape na poslužiteljima organizacije, dijeljene mape (SMB) i SSH poslužitelje (SFTP), i s njihovim datotekama radi ondje gdje jesu, bez kopiranja u Ponistru.

## Kako se koristi

### Otvaranje lokacije

1. U bočnom stupcu Dokumenata pritisnite {t:locations.title}.
2. Popis pokazuje lokacije koje ste dodali i one koje su s vama podijeljene, svaku s nazivom, pod {t:locations.address} s adresom i pod {t:locations.owner} s vlasnikom. Pritisnite lokaciju.
3. Mapu otvarate pritiskom na njezin redak, a natrag se vraćate kroz put u naslovu.
4. {t:files.refresh} ponovno čita mapu s poslužitelja.

Dok nema nijedne lokacije, piše {t:locations.none} uz poveznicu na [postavke lokacija](help:documents/locations).

### Otvaranje i uređivanje datoteke

1. Pritisnite datoteku. Tekstualna datoteka otvara se u uređivaču na mjestu popisa, a PDF, slika, zvuk i videozapis u novoj kartici preglednika.
2. Nakon izmjene teksta pritisnite {t:workspace.files.save} ili {k:Mod-s}. Uz naziv piše {t:workspace.files.unsaved} dok izmjene nisu spremljene, a zatim {t:workspace.files.saved}
3. {t:workspace.files.back} vraća na mapu. Ako izmjene nisu spremljene, pita {t:workspace.files.discard}
4. Ostale datoteke nude samo {t:file.download}.

Uz uključen {t:preview.title} na širokom zaslonu prvi pritisak pokazuje stavku u ploči sa strane, a otvara je dvostruki pritisak.

### Nove stavke

1. Pritisnite {t:create.new}.
2. {t:create.folder} izrađuje mapu u onoj koja je otvorena.
3. {t:create.upload} šalje datoteke s uređaja u otvorenu mapu. Isto čini povlačenje datoteka ili mapa na popis.

### Radnje nad stavkama

Izbornik se otvara desnim pritiskom ili dugim pritiskom na redak. Više stavki odabire se dugim pritiskom ili pritiskom uz Ctrl, a radnje su tada u traci iznad popisa.

- {t:tree.open} otvara stavku.
- {t:file.download} preuzima datoteku na uređaj.
- {t:tree.rename} mijenja naziv jedne stavke.
- {t:tree.move} otvara mape lokacije; pritisnite {t:tree.moveHere} u odredišnoj.
- {t:files.delete} briše odabrano s poslužitelja, nakon pitanja {t:files.deleteHeading}
- {t:locations.copy} otvara mape Ponistre; {t:locations.copyHere} kopira odabrano u odabranu mapu.

## Kako radi

Ponistra se na poslužitelj prijavljuje računom upisanim u lokaciji, pa na njemu smijete ono što smije taj račun, a ne vaš. Datoteke ostaju na poslužitelju: Ponistra ih ne indeksira, ne pretražuje i ne čuva im verzije, a popis mape čita svaki put kad je otvorite.

Spremanje teksta provjerava je li datoteka na poslužitelju ista kao kad ste je otvorili. Ako ju je netko u međuvremenu promijenio, piše {t:workspace.files.changed} i birate {t:workspace.files.reload} ili {t:workspace.files.overwrite}.

Kopiranje u Ponistru radi u pozadini kao posao {t:job.copy}: datoteke koje Ponistra zna pročitati (Word, Excel, PowerPoint, PDF, tekst) postaju dokumenti, ostale datoteke, a mapa se kopira sa svime što sadrži. Kopija nakon toga nema veze s izvornikom.

Brisanje na poslužitelju je trajno: Ponistrino smeće ga ne čuva. Mapa se briše sa svime u njoj.

Prva promjena na lokaciji može tražiti [potvrdu da ste to vi](help:account/confirm).

## Ograničenja

- Tko lokaciju samo čita, ima onemogućene {t:create.new}, {t:tree.rename}, {t:tree.move} i {t:files.delete}.
- U uređivaču se otvara tekst do 1 MB; za veći piše {t:workspace.files.large} Datoteka koja nije tekst javlja {t:workspace.files.binary}
- Jednim kopiranjem prenosi se najviše 1.000 stavki.
- Poveznice na poslužitelju koje vode izvan mape lokacije ne otvaraju se.
- {t:error.location_unreachable} i {t:error.location_closed} znače da poslužitelj ne odgovara; pokušajte ponovno ili provjerite mrežu do njega.
- {t:error.location_login} i {t:error.location_secret_lost} rješava vlasnik lokacije ponovnim upisom prijave u [postavkama](help:documents/locations).
- {t:error.location_host_key_changed} Vlasnik to čini tek kad je provjerio da je poslužitelj doista onaj pravi.
- {t:error.location_denied} znači da račun lokacije na poslužitelju nema to pravo.
- Poruke {t:error.file_exists} {t:error.file_missing} {t:error.file_busy} opisuju stanje na poslužitelju; osvježite popis.

## Povezano

- [Mrežne lokacije](help:documents/locations)
- [Organiziranje dokumenata](help:documents/organising)
- [Učitavanje datoteka](help:documents/upload)
