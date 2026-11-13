# Lozinka

Lozinkom računa prijavljujete se u Ponistru i potvrđujete osjetljive radnje kad nemate pristupni ključ.

## Kako se koristi

1. U Postavkama otvorite {t:password.title}.
2. Upišite {t:password.new}.
3. Pritisnite {t:password.change}.
4. Ako Ponistra zatraži, potvrdite da ste to vi.
5. Kad je gotovo, ispod polja piše: {t:password.changed}

## Kako radi

Ponistra lozinku ne čuva, nego samo njezin sažetak iz kojeg se lozinka ne može pročitati. Preglednik u kojem ste je promijenili ostaje prijavljen.

Lozinka računa nije lozinka sefa. Sef ima svoju lozinku, koju ova promjena ne dira.

Administrator instalacije u njezinu dnevniku vidi da je lozinka promijenjena, nikad samu lozinku.

## Ograničenja

Nova lozinka mora imati barem 8 znakova, ne smije biti samo od brojki, ne smije biti preslična vašem imenu ili adresi e-pošte i ne smije biti među često korištenim lozinkama. Ako nije takva, ispod polja piše što joj nedostaje.

Ako je administrator za vaš račun propisao prijavu pristupnim ključem, lozinkom se prijavljujete samo dok ključ ne dodate.

Kad se prijavljujete lozinkom iz imenika organizacije, lozinka se mijenja u imeniku, a ovdje piše {t:error.password_in_directory}

## Povezano

- [Potvrda identiteta](help:account/confirm)
- [Pristupni ključevi](help:account/passkeys)
- [Lozinka i kod sefa](help:vault/recovery)
