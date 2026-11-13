# Lozinke aplikacija

Lozinka aplikacije služi aplikaciji na uređaju koja se ne može prijaviti pristupnim ključem, poput kontakata i kalendara na iPhoneu, da čita vaše kontakte i kalendare iz Ponistre.

## Kako se koristi

### Lozinka za drugu aplikaciju

1. U Postavkama otvorite {t:appPasswords.title}.
2. Pritisnite {t:appPasswords.otherOpen} Otvara se dijalog {t:appPasswords.other}.
3. Upišite {t:appPasswords.newName} i pritisnite {t:appPasswords.add}. Dok traje, gumb prikazuje: {t:appPasswords.adding}
4. Dijalog prikazuje {t:appPasswords.password}. Pritisnite {t:appPasswords.copy} ili je prepišite.
5. Na uređaju dodajte račun CardDAV ili CalDAV i upišite {t:appPasswords.server} i {t:appPasswords.user} koje dijalog prikazuje, uz tu lozinku. Za iPhone dijalog navodi i put kroz njegove postavke.

### Uklanjanje lozinke

1. U retku uređaja otvorite izbornik radnji.
2. Odaberite {t:appPasswords.delete} i potvrdite u dijalogu {t:appPasswords.deleteTitle}

## Kako radi

Lozinka se izrađuje nasumično, od 16 slova i brojki u skupinama po 4. Ponistra čuva samo njezin sažetak, pa je poslije ne može ponovno prikazati. Popis prikazuje svaki {t:appPasswords.device}, kada je lozinka napravljena i {t:appPasswords.used}. Upotreba se bilježi najviše svakih 10 minuta. Dok lozinke nema, piše: {t:appPasswords.none}

Na ovom su popisu i lozinke koje je Android aplikacija Ponistre dobila povezivanjem telefona. Kad napravite novu lozinku, preglednici u kojima ste uključili obavijesti dobivaju obavijest o tome.

Uklanjanjem lozinke uređaj s njom više ne može pristupiti vašim kontaktima i kalendarima.

Administrator instalacije u njezinu dnevniku vidi kada je lozinka aplikacije dodana ili uklonjena, s njezinim imenom, nikad samu lozinku.

## Ograničenja

- Lozinka se prikazuje samo jednom, odmah nakon izrade. Ako je izgubite, uklonite je i napravite novu.
- Lozinka aplikacije ne vrijedi za prijavu u Ponistru u pregledniku.
- Lozinka prestaje vrijediti kad je račun deaktiviran.
- Za izradu lozinke Ponistra može zatražiti potvrdu da ste to vi.

## Povezano

- [Potvrda identiteta](help:account/confirm)
- [Prijavljeni uređaji](help:account/devices)
- [Android aplikacija](help:phone/android)
