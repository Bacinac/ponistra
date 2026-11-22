# VPN tuneli

Tunel otvara instalaciji stalnu vezu u drugu mrežu, kroz WireGuard ili SoftEther, i pokazuje je li ta veza spojena.

## Kako se koristi

### Novi tunel

1. Otvorite {t:admin.title} i odaberite {t:network.title}.
2. Pod {t:network.tunnels} pritisnite {t:network.tunnelNew}.
3. Upišite {t:network.tunnelName} po kojem ćete tunel prepoznati.
4. Pod {t:network.tunnelKind} odaberite WireGuard ili SoftEther.
5. Za WireGuard zalijepite u {t:network.configuration} konfiguraciju koju ste dobili od administratora druge mreže ili pritisnite {t:network.configurationFile} i odaberite datoteku `.conf`.
6. Za SoftEther upišite {t:network.server}, {t:network.port} (zadano 443), {t:network.hub}, {t:network.username} i {t:network.password}.
7. Ostavite označeno {t:network.tunnelEnabled} i pritisnite {t:tree.create}.

### Promjena, isključivanje i uklanjanje

1. U retku tunela otvorite {t:tree.actions}.
2. {t:network.tunnelEdit} otvara isti obrazac bez izbora vrste. Polja tajne ostaju prazna uz natpis {t:network.configurationReplace} ili {t:network.passwordReplace}: prazno polje zadržava spremljenu tajnu, nova vrijednost je zamjenjuje. Pritisnite {t:tree.save}.
3. {t:network.tunnelOff} zatvara vezu, a tunel ostaje spremljen; {t:network.tunnelOn} je ponovno otvara.
4. {t:network.tunnelDelete} nakon potvrde zatvara vezu i briše tunel zajedno sa spremljenom tajnom.

## Kako radi

Tunele drži zaseban servis instalacije, `tunnel`. Poslužitelj mu ih predaje pri svakom spremanju i sam ih ponovno predaje kad se servis pokrene iznova, pa tuneli nakon ponovnog pokretanja poslužitelja ili nadogradnje rade bez vaše radnje. Kroz tunel idu samo veze koje otvara Ponistra, a to su [mrežne lokacije](help:documents/locations) kojima je korisnik odabrao tunel; poslužitelj na kojem je instalacija i njegove druge mreže ne usmjeravaju se kroz njega.

Konfiguracija WireGuarda i lozinka SoftEthera čuvaju se zapečaćene tajnim ključem instalacije i više se ne prikazuju. U retku tunela stoje vrsta, adresa druge strane (Endpoint za WireGuard, poslužitelj i port za SoftEther) i, dok je tunel spojen, adresa koju instalacija ima u drugoj mreži.

Stanje desno u retku mijenja se samo, čim ga servis javi; zadržite pokazivač na njemu za vrijeme od kad traje:

- {t:network.state.connecting}: tunel je tek predan ili se veza ponovno uspostavlja.
- {t:network.state.up}: veza radi.
- {t:network.state.failed}: veza se nije mogla otvoriti; ispod naziva piše zašto.
- {t:network.state.off}: tunel je isključen.
- {t:network.state.unreached}: poslužitelj ne dobiva odgovor od servisa `tunnel`; tuneli se ponovno predaju čim se javi.

WireGuard radi unutar servisa i od poslužitelja instalacije ne traži ni uređaj ni posebna prava. Uzima adresu, ključeve, DNS poslužitelje i peerove iz konfiguracije; adresa bez maske dobiva /32. Kad peer ne zada PersistentKeepalive, šalje se svakih 25 sekundi, da veza ostane otvorena kroz NAT. Tunel je {t:network.state.up} dok je posljednja razmjena ključeva s peerom mlađa od 3 minute. Ime poslužitelja u Endpointu razrješava se ponovno najviše jednom u minuti, pa tunel prati promjenu adrese druge strane.

SoftEther se spaja na virtualni hub poslužitelja SoftEther VPN korisničkim imenom i lozinkom, adresu u drugoj mreži dobiva od njezina DHCP-a, a imena razrješava preko DNS poslužitelja koje taj DHCP navede. Svaki tunel ima vlastitu tablicu usmjeravanja, pa se dva tunela u mreže s istim adresama ne sudaraju. Kad veza padne, ponovno se spaja svakih 15 sekundi.

Dodavanje, promjena i uklanjanje tunela bilježe se u [dnevnik](help:admin/journal) kao {t:journal.setting.network_tunnel} s nazivom tunela.

## Ograničenja

- Tunele vidi i mijenja samo administrator, a spremanje, promjena i uklanjanje traže [ponovnu potvrdu](help:account/confirm).
- Vrsta tunela ne mijenja se nakon spremanja; za drugu vrstu dodajte novi tunel.
- SoftEther se prijavljuje samo lozinkom, ne certifikatom, i ne provjerava certifikat poslužitelja.
- SoftEther treba uređaj `/dev/net/tun` od poslužitelja instalacije; WireGuard ga ne treba.
- Iz konfiguracije WireGuarda ne čitaju se postavke koje koristi samo `wg-quick` (Table, PostUp, SaveConfig i slično) ni DNS domene za pretraživanje.

Poruke ispod naziva tunela:

- {t:network.tunnelError.no_answer}: poslužitelj druge strane nije odgovorio. Provjerite adresu i port te da vatrozid druge strane pušta promet s javne adrese instalacije.
- {t:network.tunnelError.refused}: korisničko ime, lozinka ili ključ nisu prihvaćeni. Upišite ih ponovno ili zatražite nove.
- {t:network.tunnelError.no_hub}: na poslužitelju SoftEther nema huba tog naziva; provjerite {t:network.hub}.
- {t:network.tunnelError.no_device}: poslužitelj instalacije ne daje uređaj `/dev/net/tun`. Vlasnik poslužitelja ga dodaje prema uputama za instalaciju.
- {t:network.tunnelError.dhcp}: veza je otvorena, ali DHCP druge mreže nije dodijelio adresu. Na strani SoftEthera mora raditi DHCP (SecureNAT ili mrežni).
- {t:network.tunnelError.resolve}: ime iz Endpointa ne razrješava se; provjerite ga.
- {t:network.tunnelError.sealed} Otvorite {t:network.tunnelEdit} i ponovno upišite konfiguraciju ili lozinku.
- {t:network.tunnelError.failed}: ostali razlozi; tekst iza poruke je odgovor servisa.
- {t:error.invalid_wireguard} Konfiguracija nema jedno [Interface] s PrivateKey i Address ili barem jedan [Peer] s PublicKey i Endpoint, ili ključ nije ključ WireGuarda.
- {t:error.tunnel_taken} Odaberite drugi naziv.
- {t:error.tunnel_in_use} Tunel se ne uklanja dok kroz njega ide ijedna lokacija; isključite ga ili vlasnici lokacija odaberu drugi tunel.

## Povezano

- [Mreža](help:admin/network)
- [Dnevnik](help:admin/journal)
- [Mrežne lokacije](help:documents/locations)
