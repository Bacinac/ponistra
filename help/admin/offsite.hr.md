# Kopija izvan poslužitelja

Sigurnosne kopije instalacije šifrirane se preslikavaju u spremnik S3 izvan poslužitelja koji odbija brisanje, a paket za oporavak s njima vraća instalaciju na novom poslužitelju.

## Kako se koristi

### Postavljanje spremnika

1. Na stranici {t:health.title}, pod {t:health.offsite}, pritisnite {t:health.offsite.set} ili, kad je kopija već postavljena, {t:health.offsite.change}
2. Kod pružatelja, primjerice Cloudflare R2, otvorite spremnik i ključ za pristup kako opisuje uputa u dijalogu.
3. Upišite {t:health.offsite.endpoint}, {t:health.offsite.bucket}, {t:health.offsite.accessKey} i {t:health.offsite.secret}.
4. Pritisnite {t:health.offsite.save}. Dok traje, gumb prikazuje: {t:health.offsite.checking}
5. U dijalogu {t:health.kit.title} pritisnite {t:health.kit.copy} ili {t:health.kit.download} i spremite paket izvan poslužitelja.

### Novi paket za oporavak

1. Pritisnite {t:health.kit.renew}
2. Potvrdite gumbom {t:health.kit.renewConfirm} i spremite novi paket kao pri postavljanju.

## Kako radi

Prije spremanja Ponistra provjerava odgovara li spremnik na unesene ključeve. Tajni ključ sprema se zaključan; poslije piše samo {t:health.offsite.secretKept} i njegova zadnja četiri znaka. Prazno polje ostavlja spremljeni tajni ključ samo dok su adresa, spremnik i ključ za pristup isti. Ako se spremljeni ključ više ne može pročitati, piše: {t:health.offsite.secretLost}

Svaka nova sigurnosna kopija, i promjene baze i datoteke spremljene svakih 15 minuta između njih, preslikava se datoteku po datoteku najkasnije 10 minuta nakon što nastane; u spremnik se samo dodaje. Propadne li poslužitelj, `ponistra recover` vraća instalaciju na posljednji tako preslikan trenutak. Ponistra pokušava izbrisati probnu datoteku u spremniku, pa pod {t:health.offsite.protection} piše {t:health.offsite.protected} ili {t:health.offsite.unprotected}. Svakih 28 dana započinje nova cjelovita kopija sa svim datotekama, a uz {t:health.offsite.generation} piše kada je započela; starije odlaze kako im istječe zaključavanje. Dok najnovija kopija nije preslikana, piše: {t:health.offsite.late}

Jednom dnevno, nakon preslikavanja, kopija u spremniku se provjerava, svake noći drugi dio podataka, tako da se svaki dio pročita unutar 28 dana. Svakih 30 dana, ili nakon neuspjelog pokušaja, Ponistra najnoviju kopiju iz spremnika sa svim promjenama baze spremljenima nakon nje probno vraća u zasebnu bazu, provjerava ima li spremnik svaku datoteku koju ta baza navodi i zatim je uklanja. Uz {t:health.offsite.mirrored}, {t:health.offsite.checked} i {t:health.offsite.tried} piše kada se što posljednji put dogodilo, a ispod koliko je dokumenata, mapa i datoteka probni povrat vratio.

### Paket za oporavak

Paket sadrži adresu, spremnik, ključ za pristup, tajni ključ i ključ za nuždu. Ključ za nuždu prikazuje se samo u tom dijalogu i ne čuva se nigdje drugdje. Svako spremanje spremnika i svaki novi paket izrađuju novi ključ za nuždu, a dosadašnji uklanjaju s poslužitelja. S paketom se instalacija naredbom `ponistra recover` vraća na novom poslužitelju.

## Ograničenja

- Tko ima paket za oporavak, može pročitati sve sigurnosne kopije.
- Dok se radi sigurnosna kopija, spremnik se ne može promijeniti ni paket izraditi.
- Za spremanje spremnika i novi paket Ponistra može zatražiti potvrdu da ste to vi.

## Povezano

- [Stanje sustava](help:admin/health)
- [Potvrda identiteta](help:account/confirm)
