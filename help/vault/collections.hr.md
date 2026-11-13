# Dijeljene zbirke sefa

Zbirka je dio sefa koji dijelite s korisnicima ili grupama, tako da svi članovi vide iste lozinke.

## Kako se koristi

### Nova zbirka

1. U lijevom stupcu sefa uz {t:vault.shared} pritisnite {t:vault.newCollection}.
2. Upišite naziv i pritisnite {t:tree.create}.

### Članovi

1. Otvorite zbirku i u izborniku ostalih radnji odaberite {t:vault.members}. Isti izbornik otvara se desnim klikom ili dugim pritiskom na zbirku ili mapu u lijevom stupcu.
2. Pod {t:access.who} odaberite {t:access.everyone}, osobu iz {t:access.people} ili grupu iz {t:access.groups}.
3. Odaberite {t:access.role}: {t:access.role.read}, {t:access.role.edit} ili {t:access.role.own}, pa pritisnite {t:access.add}.
4. Ulogu člana mijenjate u njegovu retku, a pomoću {t:access.remove} ga uklanjate.
5. Pod {t:vault.waiting} pritisnite {t:vault.confirm} uz člana, ili {t:vault.confirmAll}.
6. Članstvo u tuđoj zbirci napuštate pomoću {t:vault.leave}.

### Zbirka i njezin dnevnik

1. Vlasnik u izborniku ostalih radnji odabire {t:log.title}: {t:log.when}, {t:log.who} i {t:log.what}.
2. Vlasnik zbirku preimenuje pomoću {t:tree.rename}.
3. Ili je briše pomoću {t:vault.deleteCollection}, uz potvrdu u dijalogu {t:vault.deleteCollectionTitle}

## Kako radi

Svaka zbirka ima svoj ključ, kojim su šifrirane njezine stavke. Član vidi stavke tek kad mu vlasnik potvrdi članstvo: potvrdom preglednik vlasnika šifrira ključ zbirke za tog člana. Kad dodate osobu koja već ima sef, potvrđuje se odmah. Tko još nema sef, naveden je kao {t:vault.unset} i čeka potvrdu kad ga izradi. Broj članova koji čekaju piše uz zbirku u lijevom stupcu, a zbirka čiji ključ još nemate označena je kao {t:vault.pending}.

{t:access.role.read} dopušta gledanje i kopiranje, {t:access.role.edit} i dodavanje, mijenjanje i premještanje stavki, a {t:access.role.own} i članove, dnevnik, izvoz, trajno brisanje iz smeća te preimenovanje i brisanje zbirke.

Dnevnik bilježi {t:vault.log.opened}, {t:vault.log.password}, {t:vault.log.totp}, {t:log.kind.shared}, {t:log.unshared}, {t:vault.log.confirmed} i {t:vault.log.exported}. Ponovljeno otvaranje i prikaz iste lozinke istog korisnika ne bilježe se ponovno unutar sat vremena. Obrisana stavka u dnevniku stoji kao {t:vault.log.gone}, a obrisani korisnik kao {t:log.formerUser}. Dok nema zapisa, piše: {t:vault.log.none}

Zbirke koje je dala tvrtka stoje pod {t:tree.company}. Njihove članove određuje administrator, a vlasnici ih potvrđuju. Zbirku tvrtke koju još nitko nije otvorio njezin vlasnik otvara pomoću {t:vault.firstKey}, a zatim potvrđuje ostale. Administrator koji nije član ne može je pročitati.

Obrisana zbirka nestaje sa svim stavkama, za sve članove.

## Ograničenja

- Zbirka mora uvijek imati barem jednog vlasnika, pa posljednjeg ne možete ukloniti ni promijeniti mu ulogu.
- Zbirku tvrtke ne možete napustiti ni preimenovati; to radi administrator.
- Član koji izradi novi sef ispočetka mora ponovno biti potvrđen.

## Povezano

- [Stavke sefa](help:vault/items)
- [Uvoz i izvoz sefa](help:vault/transfer)
- [Sef](help:vault/overview)
