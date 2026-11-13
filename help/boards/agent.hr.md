# Slanje ploče agentu

Gumb {t:board.agent} iznad ploče otvara novi razgovor s agentom u vašem radnom prostoru za kod, sa zadatkom da provede odgovore upisane na ploči.

## Kako se koristi

### Prvo slanje

1. Otvorite ploču.
2. Pritisnite {t:board.agent} na traci iznad ploče.
3. U polju {t:board.agentProject} odaberite projekt u kojem agent radi i pritisnite {t:board.agent}.
4. U radnom prostoru otvara se novi razgovor s upisanim zadatkom. Pregledajte ga i pokrenite tipkom Enter.

### Sljedeća slanja

1. Pritisnite {t:board.agent}. Razgovor se otvara u projektu koji ste odabrali prvi put.

### Drugi projekt

1. U izborniku ploče odaberite {t:board.agentFolder}
2. Odaberite projekt i pritisnite {t:tree.save}.

## Kako radi

Zadatak koji gumb upisuje imenuje ploču i traži od agenta da provede odluke na koje je upisan odgovor. Ništa se ne šalje dok ne pritisnete Enter u razgovoru.

Projekt se pamti uz ploču, pa ga vidi i svatko s kim ploču dijelite. Odabrati ga smije samo onaj tko ploču smije uređivati. Sama stranica ploče ne može otvoriti razgovor ni promijeniti projekt, jer je zatvorena u vlastitom okviru.

## Ograničenja

- Gumb vidi samo korisnik kojemu pripada radni prostor za kod, kako opisuje članak [Projekti](help:agents/projects).
- Dok projekt nije odabran, gumb ne vidi onaj tko ploču smije samo čitati.
- Projekti na popisu dolaze iz radnog prostora; dok se on ne javlja, projekt se ne može odabrati.

## Povezano

- [Ploče](help:boards/overview)
- [Projekti](help:agents/projects)
