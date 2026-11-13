# Lozinka, kod i pristupni ključevi sefa

U postavkama sefa mijenjate njegovu lozinku, prikazujete ili obnavljate kod za oporavak i uključujete otključavanje pristupnim ključem.

## Kako se koristi

### Postavke sefa

1. U otključanom sefu pritisnite {t:vault.settings} na dnu lijevog stupca.
2. Pod {t:vault.password.change} upišite {t:vault.password.new} i ponovite je, pa pritisnite {t:vault.password.change}. Kad je gotovo, piše: {t:vault.password.changed}
3. Pod {t:vault.code} pritisnite {t:vault.codeShow} da vidite dosadašnji kod, ili {t:vault.codeRenew} za novi.
4. Pod {t:vault.passkeys} pritisnite {t:vault.passkeyAdd} i potvrdite jednim od svojih pristupnih ključeva. Uz svaki ključ na popisu je {t:vault.passkeyRemove}.
5. Pod {t:vault.recovery} piše može li tvrtka oporaviti vaš sef i, ako je to već učinila, {t:vault.recoveredBy}.

### Zaboravljena lozinka

1. Na zaključanom sefu pritisnite {t:vault.forgot}.
2. Upišite {t:vault.code} i pritisnite {t:vault.unlock}.
3. Sef traži novu lozinku: upišite je dvaput i pritisnite {t:vault.password.set}.
4. Za povratak na lozinku pritisnite {t:vault.withPassword}.

### Kod od administratora

1. Kad vam je administrator pripremio kod za oporavak, zaključan sef odmah traži {t:vault.code}.
2. Upišite kod koji ste od njega dobili i pritisnite {t:vault.unlock}.
3. Postavite novu lozinku sefa i pritisnite {t:vault.password.set}.

### Početak ispočetka

1. Ako nemate ni lozinku ni kod, pritisnite {t:vault.forgot}.
2. Pritisnite {t:vault.restart} i potvrdite u dijalogu {t:vault.restartTitle}

## Kako radi

Kod za oporavak izrađuje se pri izradi sefa i otvara ga kao i lozinka. Novi kod poništava dosadašnji. Nakon otvaranja kodom sef ne pušta dalje dok ne postavite novu lozinku, a piše: {t:vault.password.afterCode}

Otključavanje pristupnim ključem koristi pristupne ključeve za prijavu u Ponistru. Sef se otključava samo ključem koji uz prijavu daje i tajnu za šifriranje, što podržavaju Android, iPhone, Mac i Windows 11 s novijim preglednikom.

Kad je tvrtka uključila oporavak sefova, sef se pri sljedećem otključavanju zaključava i ključem tvrtke. Tada piše: {t:vault.recoverable} Ako to ne uspije, piše: {t:vault.enrolFailed} Svaki oporavak koji administrator napravi vidite pod {t:vault.recoveredBy}, i na zaključanom sefu i u postavkama.

Početak ispočetka briše Moj sef sa svim stavkama, lozinkom, kodom i otključavanjem pristupnim ključem. Dijeljene zbirke ostaju drugim članovima, a u njih se vraćate kad vas vlasnik ponovno potvrdi.

## Ograničenja

- Kad kod nije ispravan, piše: {t:vault.wrongCode}
- {t:vault.noPrf}
- Promjena lozinke, otključavanje pristupnim ključem i početak ispočetka mogu tražiti potvrdu da ste to vi.
- Početak ispočetka ne može se poništiti.
- Administrator koji jedini drži ključ oporavka sefova ne može početi ispočetka dok ga ne preda drugom administratoru.

## Povezano

- [Sef](help:vault/overview)
- [Pristupni ključevi](help:account/passkeys)
- [Potvrda identiteta](help:account/confirm)
