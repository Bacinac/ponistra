# Oporavak sefova

Kad je oporavak sefova uključen, administrator može korisniku koji je zaboravio i lozinku i kod sefa pripremiti jednokratni kod za ulaz u sef.

## Kako se koristi

### Uključivanje

1. Izradite i otključajte svoj sef.
2. Na stranici {t:users.title}, u odjeljku {t:recovery.title}, gdje piše {t:recovery.off} pritisnite {t:recovery.turnOn}.
3. Drugog administratora koji ima sef, a nalazi se pod {t:recovery.waiting}, potvrdite gumbom {t:vault.confirm}.

### Oporavak sefa korisnika

1. Otključajte svoj sef.
2. U izborniku retka korisnika odaberite {t:recovery.recover}.
3. Pritisnite {t:recovery.prepare}.
4. Kod predajte korisniku osobno, ne poštom ni porukom.

### Isključivanje

1. Pritisnite {t:recovery.turnOff}.
2. Potvrdite u dijalogu {t:recovery.turnOffTitle}

## Kako radi

Ključ oporavka izrađuje preglednik administratora koji je oporavak uključio i zaključava ga njemu; svaki potvrđeni administrator dobiva svoj primjerak. Svaki se sef pri sljedećem otključavanju zaključava i ključem tvrtke. Odjeljak pokazuje tko je oporavak uključio i kada ({t:recovery.on}), {t:recovery.escrowed} od ukupnog broja sefova i {t:recovery.holders}.

Kod se izrađuje u vašem pregledniku. Korisnik njime otvara sef i odmah postavlja novu lozinku; kod vrijedi dok to ne učini. Tko može oporaviti sef, može ga i pročitati, pa korisnik u svojem sefu vidi tko ga je posljednji oporavio i kada.

Isključivanje briše ključ tvrtke sa svime što je njime zaključano. Korisnik koji tada zaboravi lozinku i kod više ne može otvoriti sef, a ponovno uključivanje stvara novi ključ.

## Ograničenja

- Oporavak ne pomaže dok korisnik svoj sef nije otključao otkad je oporavak uključen.
- Kod priprema i administratore potvrđuje samo administrator koji ima ključ oporavka.
- Kad korisnik nema sef, piše: {t:recovery.noVault}
- Uključivanje, isključivanje i priprema koda mogu tražiti potvrdu da ste to vi.

## Povezano

- [Korisnici](help:admin/users)
- [Lozinka, kod i pristupni ključevi sefa](help:vault/recovery)
