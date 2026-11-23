# Docker domaćini

Docker na poslužitelju do kojega instalacija dolazi SSH-om: stogovi iz mapa s compose datotekom upravljaju se u Datotekama, a kontejneri, slike, volumeni i mreže domaćina na njegovoj stranici.

## Kako se koristi

### Novi domaćin

1. U [Datotekama](/files) dodajte poslužitelj kao [SFTP lokaciju](help:documents/locations), ako već nije.
2. Otvorite {t:admin.title}, odaberite {t:network.title} i pod {t:docker.hosts} pritisnite {t:docker.hostNew}.
3. Odaberite lokaciju i pritisnite {t:docker.hostAdd}.
4. U retku domaćina pritisnite {t:docker.copyAuthorized} i dodajte kopirani redak u `~/.ssh/authorized_keys` računa te lokacije na poslužitelju. Račun mora biti u grupi `docker`.
5. U izborniku retka odaberite {t:docker.hostOpen}; kad stranica pokaže inačicu Dockera, domaćin radi.

Poruka {t:docker.noCandidates} znači da nema SFTP lokacije koju posjedujete, a koja već nije domaćin.

### Stog u Datotekama

1. U [Datotekama](/files) otvorite lokaciju domaćina pod {t:locations.title} i uđite u mapu stoga, mapu s datotekom `compose.yaml`, `compose.yml`, `docker-compose.yaml` ili `docker-compose.yml`.
2. Iznad datoteka stoji {t:docker.stack} s kontejnerima i njihovim stanjem, a uz njih {t:docker.stackDown} dok stog ne radi.
3. Pritisnite {t:docker.verb.up} za pokretanje stoga ili u izborniku do njega odaberite {t:docker.verb.pull}, {t:docker.verb.restart}, {t:docker.verb.stop} ili {t:docker.verb.down}. Prozor ispisuje što Docker Compose radi i kako je završio.
4. Compose datoteku uređujete kao svaku drugu tekstnu datoteku: otvorite je dvoklikom, a izmjenu primijenite s {t:docker.verb.up}.
5. U korijenu lokacije gumb {t:docker.host} vodi na stranicu domaćina.

### Kontejner

U izborniku retka kontejnera, u stogu ili na stranici domaćina:

- {t:docker.logs} otvara zadnjih 500 redaka zapisa i dopisuje nove dok je prozor otvoren.
- {t:docker.shell} otvara terminal u kontejneru koji radi.
- {t:docker.start}, {t:docker.stop} i {t:docker.restart} mijenjaju njegovo stanje.

### Stranica domaćina

1. Otvorite je iz retka domaćina u {t:network.title} ili gumbom {t:docker.host} u Datotekama.
2. Kartice {t:docker.kind.containers}, {t:docker.kind.images}, {t:docker.kind.volumes} i {t:docker.kind.networks} navode sve što Docker na domaćinu ima, uz oznaku {t:docker.unused} za ono što nijedan kontejner ne drži.
3. Pojedinačnu stavku koja se ne koristi uklanjate u izborniku njezina retka s {t:docker.remove}; zaustavljeni kontejner također.
4. Gumbi iznad popisa uklanjaju sve nekorišteno odjednom: {t:docker.prune.containers}, {t:docker.prune.images}, {t:docker.prune.builder}, {t:docker.prune.volumes} i {t:docker.prune.networks}. Nakon potvrde ispod stoji koliko je uklonjeno i koliko je mjesta oslobođeno.

### Uklanjanje domaćina

1. U {t:network.title} u izborniku retka domaćina odaberite {t:docker.hostRemove} i potvrdite.
2. Na poslužitelju izbrišite redak iz `authorized_keys`.

## Kako radi

Instalacija za svaki domaćin stvara vlastiti ključ ed25519 i čuva ga zapečaćenog tajnim ključem instalacije; ključ lokacije za datoteke ostaje zaseban. Redak za `authorized_keys` nosi prisilnu naredbu: tim ključem poslužitelj izvodi samo `docker system dial-stdio`, kojim instalacija razgovara s Dockerovim API-jem, i `docker compose` s jednom od pet radnji stoga u zadanoj mapi. Na svaku drugu naredbu stranica javlja {t:error.docker_command_refused} uz ono što je poslužitelj rekao. Docker na domaćinu vrijedi koliko i root na njemu, pa ga vide i mijenjaju samo administratori.

Veza ide istim putem kao datoteke lokacije: isti poslužitelj, ključ poslužitelja koji je lokacija upamtila, posredni poslužitelj i [VPN tunel](help:admin/tunnels) ako ga lokacija koristi. Domaćina dodaje vlasnik lokacije; administrator s kojim je lokacija podijeljena za uređivanje upravlja njime, a onaj koji je smije samo čitati vidi stanje i zapise.

{t:docker.verb.up} izvodi `docker compose up -d --remove-orphans`, pa se kontejneri koje je compose datoteka izgubila uklanjaju. Svaka izmjena na domaćinu traži [ponovnu potvrdu](help:account/confirm) ako zadnja nije svježa.

Instalacija prati događaje Dockera na svakom domaćinu, pa se stog, popisi i stanja na otvorenim stranicama osvježavaju sami kad se kontejner pokrene ili zaustavi, i kad to učini netko izvan Ponistre. Kad domaćin nije dostupan, pokušava ponovno, najprije nakon pet sekundi, zatim sve rjeđe, do pet minuta.

Uklanjanje domaćina briše samo njegov ključ u instalaciji; lokacija, njezine datoteke i sve na poslužitelju ostaju.

## Ograničenja

- Docker domaćin može biti samo SFTP lokacija ({t:error.docker_needs_sftp}), i to po jedna ({t:error.docker_host_exists}).
- Prisilna naredba ne dopušta `build` ni ostale naredbe Docker Composea; slike se grade drugdje i preuzimaju s {t:docker.verb.pull}.
- Ljuska radi samo u kontejneru koji radi; koristi `bash` ako ga kontejner ima, inače `sh`.
- {t:docker.prune.volumes} briše i imenovane volumene koje nijedan kontejner ne koristi, s podacima; stog koji je spušten s {t:docker.verb.down} ostaje bez njih.
- {t:error.docker_denied} znači da račun nije u grupi: dodajte račun u grupu `docker` na poslužitelju i ponovno se prijavite tim računom.
- {t:error.docker_missing} i {t:error.docker_compose_missing} znače da na poslužitelju treba instalirati Docker Engine s dodatkom Compose.
- {t:error.docker_down} znači da Dockerov servis na poslužitelju ne radi; ispod svake poruke stoji što je Docker sam rekao.
- {t:error.docker_stack_missing} znači da je mapa u međuvremenu uklonjena ili preimenovana.
- {t:error.docker_conflict} znači da stavku još koristi kontejner; najprije ga zaustavite ili uklonite.
- {t:error.docker_secret_lost} znači da je tajni ključ instalacije promijenjen; uklonite domaćina, dodajte ga ponovno i zamijenite redak u `authorized_keys`.

## Povezano

- [Lokacije](help:documents/locations)
- [Mreža u Datotekama](help:files/network)
- [VPN tuneli](help:admin/tunnels)
- [Mreža](help:admin/network)
