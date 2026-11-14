# Umjetna inteligencija u instalaciji

Administrator uključuje Claudea i pretvaranje govora u tekst za cijelu instalaciju, unosi ključeve i prati potrošnju.

## Kako se koristi

### Claude

1. Otvorite {t:admin.title} i odaberite {t:ai.title}.
2. Upišite {t:ai.key} i označite {t:ai.enabled}.
3. Pritisnite {t:ai.save}.

### Govor u tekst

1. U odjeljku {t:speech.heading} upišite {t:speech.key}.
2. Označite {t:speech.enabled} i pritisnite {t:ai.save}.

### Mjesečni strop

1. Upišite iznos u polje {t:ai.monthly} i pritisnite {t:ai.save}.
2. Za rad bez ograničenja ostavite polje prazno ({t:ai.monthlyNone}) i spremite.

### Potrošnja i slobodne upute

1. Pod {t:ai.usage.heading} pregledajte {t:ai.usage.month}, {t:ai.usage.action}, {t:ai.usage.runs}, {t:ai.usage.input}, {t:ai.usage.output} i {t:ai.usage.cost}.
2. Pod {t:ai.requests.heading} pregledajte {t:ai.requests.request}, {t:ai.requests.times} i {t:ai.requests.last}.

## Kako radi

Radnje s Claudeom šalju tekst modelu Claude tvrtke Anthropic u SAD-u, API ključem ove instalacije. Dok je umjetna inteligencija isključena, te su radnje vidljive, ali onemogućene. Ključ se pri spremanju provjerava, sprema se zaključan i više se ne prikazuje; piše samo {t:ai.keyKept} i zadnja četiri znaka. Novi ključ upisan u isto polje zamjenjuje dosadašnji. Uz postavku piše i {t:ai.changed}.

Govor u tekst šalje izgovoreno modelu tvrtke OpenAI, a dobiveni tekst, dok je Claude uključen, Claude pretvara u događaj, zadatak ili bilješku. Svaki korisnik prije prvog snimanja daje svoj pristanak.

Strop vrijedi jednako za svakog korisnika i računa se po kalendarskom mjesecu, po vremenu instalacije. Provjerava se svaki put prije nego što se model pozove: radnja koja je već počela završava, a korisnik koji je dosegnuo strop do početka idućeg mjeseca dobiva poruku {t:error.limit_reached} Skupni posao nad mapom staje na prvoj stavci nakon što se strop dosegne. Promijenjeni strop vrijedi od sljedećeg poziva modela.

Potrošnja pokazuje tokene i trošak u američkim dolarima po mjesecu i radnji, za posljednjih dvanaest mjeseci. Osim radnji u dokumentima ondje se pojavljuju i {t:action.documentTidy}, {t:action.searchTranslate}, {t:action.mailTranslate}, {t:action.mailTranslateReply}, {t:action.fileTranslate}, {t:action.speechUnderstand} i {t:action.vaultSort}. Izvođenja modela bez cijene broje se kao {t:ai.usage.unpriced}. Slobodne upute iz izbornika {t:action.textAsk.ask} grupirane su po tekstu, bez korisnika i dokumenta.

Svaka promjena upisuje se u [dnevnik](help:admin/journal), nikad sam ključ.

## Ograničenja

- Claude se ne može uključiti bez ključa koji radi.
- Strop je jedan za sve korisnike; potrošnja pojedinog korisnika ne prikazuje se.
- Ako se promijeni tajna instalacije, spremljeni ključ više se ne može otvoriti i treba ga unijeti ponovno.
- Dok modeli nisu izveli nijednu radnju, piše: {t:ai.usage.none}
- Dok nema slobodnih uputa, piše: {t:ai.requests.none}

## Povezano

- [Radnje i Claude](help:ai/actions)
- [Pristanci](help:ai/consents)
