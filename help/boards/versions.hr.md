# Verzije ploče

Svaki put kad agent ponovno napiše ploču, prijašnja stranica ostaje kao verzija koju možete pogledati i vratiti.

## Kako se koristi

### Pregled verzije

1. Na otvorenoj ploči pritisnite {t:version.list}.
2. Pritisnite verziju u popisu. Ploča pokazuje stranicu te verzije; najnovija stoji na vrhu s oznakom {t:board.current}.

### Vraćanje verzije

1. Desni klik ili dugi pritisak na verziju otvara {t:version.restore}.
2. U dijalogu {t:board.restoreTitle} potvrdite s {t:version.restore}. {t:board.restoreWarning}

## Kako radi

Uz svaku verziju stoje njezin broj, datum, tko ju je napisao i kroz kojeg agenta. Vraćena verzija postaje nova verzija s nazivom {t:version.restoredFrom} i brojem one iz koje je vraćena.

Verzija čuva samo stranicu ploče; podaci koje ploča čuva ne vraćaju se s njom.

## Ograničenja

- Vratiti verziju može samo onaj tko smije uređivati ploču; trenutna verzija ne vraća se.
- Dok ploča nema drugih verzija, piše: {t:board.versionsEmpty}

## Povezano

- [Ploče](help:boards/overview)
