# Šifrirana i potpisana pošta

Ponistra čita i šalje poruke potpisane i šifrirane po standardima S/MIME i OpenPGP, ključem koji čuvate u sefu.

## Kako se koristi

### Čitanje šifrirane poruke

1. Otvorite poruku označenu lokotom. Iznad nje piše {t:mail.sealed.encrypted}.
2. Kad je sef zaključan, piše {t:mail.sealed.locked} Upišite lozinku sefa i pritisnite {t:vault.unlock}, ili ga otključajte pristupnim ključem.
3. Poruka se otvara s tekstom, slikama i privitcima. Privitak preuzimate pritiskom na njegov naziv.

### Provjera potpisa

Iznad potpisane poruke piše ishod provjere:

- {t:mail.signed.valid}, uz adresu potpisnika.
- {t:mail.signed.changed}. Ako znate da je pošiljatelj promijenio ključ, pritisnite {t:mail.signed.accept}.
- {t:mail.signed.mismatch}, uz adresu na koju potpis glasi.
- {t:mail.signed.expired}
- {t:mail.signed.invalid}
- {t:mail.signed.unknown}. Ključ OpenPGP pošiljatelja učitajte kako je opisano niže.

### Slanje potpisane ili šifrirane poruke

1. U obrascu poruke pritisnite {t:mail.sealing.sign}, {t:mail.sealing.encrypt} ili oboje. Gumbi se prikazuju kad u sefu imate ključ pošte ili odgovarate na šifriranu poruku.
2. Kad je sef zaključan, otključajte ga ispod obrasca.
3. Pritisnite {t:mail.send} ili {t:mail.later}.

### Ključevi primatelja

1. Otvorite Postavke pa {t:mail.senders}.
2. Pod {t:mail.keys} su Vaši objavljeni ključevi s oznakom {t:mail.keysOwn} i ključevi pošiljatelja koje je Ponistra zapamtila ({t:mail.keysNone} kad ih nema).
3. Pritisnite {t:mail.keysBring} i odaberite javni ključ OpenPGP (`.asc`) ili certifikat (`.cer`, `.crt`, `.pem`) osobe kojoj želite pisati šifrirano.
4. Pritisnite {t:mail.keysRemove} uz ključ koji više ne vrijedi.

## Kako radi

Šifrirana poruka otvara se u pregledniku ključem iz sefa. Otvoreni sadržaj šalje se poslužitelju samo da ga pročita kao svaku poruku i očisti HTML; poslužitelj ga ne sprema. Slike s drugih poslužitelja u šifriranoj se poruci nikad ne učitavaju, kako pošiljatelj ne bi saznao da je otvorena. Kad zatvorite poruku, otvoreni sadržaj nestaje i iz preglednika.

Ključ pošiljatelja pamti se kad prvi put pročitate njegovu valjano potpisanu poruku, ili iz zaglavlja Autocrypt koje šalju alati OpenPGP. Ako kasnije potpiše drugim ključem, to se javlja dok novi ključ ne prihvatite. Zapamćene ključeve vidite samo Vi, a ključeve koje su kolege objavile iz svojeg sefa vidi cijela instalacija.

Šifrirana poruka šifrira se svakom primatelju i Vama. Koristi se oblik Vašeg ključa za adresu pošiljatelja, S/MIME ili OpenPGP, za koji svi primatelji imaju ključ. S/MIME poruka koja je i potpisana nosi potpis unutar šifre, a OpenPGP potpisuje unutar šifrirane poruke.

Odgovor na šifriranu poruku zadano je šifriran i citira otvoreni tekst. Proslijeđena šifrirana poruka nosi svoje privitke otvorene, kao privitke nove poruke.

## Ograničenja

- Predmet, pošiljatelj i primatelji nisu šifrirani, samo tijelo i privitci.
- Ponistra provjerava da je potpis valjan i da certifikat glasi na adresu pošiljatelja, a ključ pamti pri prvoj poruci. Ne provjerava lanac certifikata do izdavatelja ni njegov opoziv.
- Tražilica ne pronalazi tekst šifriranih poruka.
- Šifrirana poruka ne može dijeliti dokumente poveznicom; priložite ih kao datoteke.
- Odgovor na šifriranu poruku spremljen kao nedovršen ne čuva citirani tekst.
- Kad poruka nije šifrirana nijednim Vašim ključem, piše: {t:smime.notForMe} ili {t:pgp.notForMe}
- Šifriranje 3DES, ključevi ECDH i S/MIME s autentificiranim šifriranjem nisu podržani. Tada piše: {t:smime.unsupported} ili {t:pgp.unsupported}
- Kad nemate sef, piše {t:mail.sealed.noVault} a kad u sefu nema ključa pošte, {t:mail.sealed.noKeys} Ključ dodajte u sef.
- Kad u sefu nema ključa za adresu s koje šaljete, piše {t:mail.sealing.noOwnKey} uz adresu.
- Kad za nekog primatelja nema ključa, piše {t:mail.sealing.noKeys} uz njegove adrese. Učitajte njegov ključ ili isključite {t:mail.sealing.encrypt}.
- Kad datoteka nije ključ ni certifikat, piše: {t:pgp.notKey} ili {t:smime.notCertificate}

## Povezano

- [Ključevi pošte u sefu](help:vault/mail-keys)
- [Čitanje poruke](help:mail/reading)
- [Pisanje poruke](help:mail/composing)
