# Učitavanje datoteka

Datoteke i cijele mape s računala učitavate među dokumente, a datoteke iz Officea i LibreOfficea pritom postaju dokumenti koje uređujete u Ponistri.

## Kako se koristi

### Iz izbornika

1. Otvorite mapu u koju učitavate.
2. Pritisnite {t:create.new} i odaberite {t:create.upload} ili {t:create.uploadFolder} pa u prozoru preglednika odaberite datoteke ili mapu.
3. Dok traje prijenos, ispod popisa piše {t:upload.progress} s brojem prenesenih datoteka i količinom podataka.

### Povlačenjem

1. Povucite datoteke ili mape s računala na popis otvorene mape.
2. Pustite ih na prazno mjesto u popisu da završe u otvorenoj mapi, ili na mapu u popisu ili u lijevom stupcu da završe u njoj.

## Kako radi

Datoteke Worda, Excela i PowerPointa te OpenDocumenta (`.docx`, `.doc`, `.rtf`, `.odt`, `.xlsx`, `.xls`, `.ods`, `.pptx`, `.ppt`, `.odp` i srodne vrste s makronaredbama i predlošcima), `.csv` te `.ponx` uvoze se u dokument. U vrlo velikoj tablici prvi se reci vide čim stignu, a ostali pristižu dok uvoz još traje. Sve ostale ostaju datoteke kakve jesu i otvaraju se u pregledu. Oznake koje preglednik izveze kao HTML postaju mapa poveznica. Što uvoz nije mogao prenijeti, dokument pokazuje u [izvještaju o uvozu](help:documents/import).

Učitana mapa zadržava svoje podmape. Datoteke i podmape čiji naziv počinje točkom preskaču se. Datum izmjene svake stavke preuzima se iz datoteke na računalu, a ne iz trenutka učitavanja.

Ako datoteku nije moguće uvesti jer je nečitljiva ili prevelika, jer radna knjiga ima previše ćelija ili različitih formula, ili jer je spremljena u novijoj inačici programa, sprema se kao obična datoteka, a ispod popisa to se navodi s razlogom. Ostale datoteke se svejedno učitavaju. Datoteke koje se nisu uopće učitale navodi redak {t:upload.failed}

Poslovi koji traju dulje od sekunde, poput uvoza, izrade kopije ili spremanja u drugi oblik, prikazuju se u okviru u donjem desnom kutu: {t:job.import}, {t:job.copy}, {t:job.saving}, {t:job.compose} ili {t:job.redact}, s nazivom i stanjem {t:job.waiting} ili {t:job.running}. Dok se posao još može prekinuti, uz njega stoji {t:tree.cancel}. Učitavanje se nastavlja i kad prijeđete na drugu stranicu.

## Ograničenja

- Učitavati možete samo u mapu u kojoj imate pravo uređivanja.
- Dok se datoteka prenosi, ispod popisa piše {t:file.uploading}
- Velike datoteke prenose se u dijelovima, a poslužitelj odbija datoteku veću od ograničenja instalacije ili kad mu ponestane prostora.

## Povezano

- [Izvještaj o uvozu](help:documents/import)
- [Pregled dokumenata](help:documents/overview)
- [Datoteke](help:files/overview)
