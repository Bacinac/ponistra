# Vanjska prijava i imenici

Administrator povezuje Ponistru s izdavateljem prijave organizacije (OpenID Connect ili SAML) i s njezinim imenikom (LDAP, Active Directory ili SCIM), pa se korisnici prijavljuju računom organizacije, a računi i grupe dolaze iz imenika.

## Kako se koristi

### Izdavatelj prijave (OpenID Connect ili SAML)

1. Na stranici {t:users.title}, u odjeljku {t:sources.title}, pritisnite {t:sources.new}.
2. Upišite {t:sources.name}, naziv koji korisnici vide na gumbu stranice prijave.
3. Pod {t:sources.kind} odaberite {t:sources.kind.oidc} ili {t:sources.kind.saml}. Za OpenID Connect upišite i {t:sources.field.issuer}.
4. Pritisnite {t:sources.next}. Dijalog sada pokazuje adrese koje upisujete kod izdavatelja, svaku s gumbom za kopiranje: za OpenID Connect {t:sources.here.redirect_uri}, za SAML {t:sources.here.entity_id}, {t:sources.here.acs_url} i {t:sources.here.metadata_url}.
5. Kod izdavatelja registrirajte Ponistru s tim adresama.
6. Za OpenID Connect upišite {t:sources.field.client_id} i {t:sources.field.secret} koje je izdavatelj dao. Za SAML upišite {t:sources.field.metadata_url} ili zalijepite {t:sources.field.metadata}.
7. Po potrebi upišite {t:sources.domains} i uključite {t:sources.creates} i {t:sources.groups}.
8. Pod {t:sources.advanced} za OpenID Connect po potrebi promijenite {t:sources.field.scopes} (zadano `openid email profile`) i {t:sources.field.groups_claim} (zadano `groups`), a za SAML {t:sources.field.email_attribute} i {t:sources.field.groups_attribute}, kad ih izdavatelj šalje pod nazivima koje Ponistra ne prepoznaje sama.
9. Ostavite uključeno {t:sources.enabled} i pritisnite {t:tree.save}.

### Imenik LDAP ili Active Directory

1. Pritisnite {t:sources.new} i pod {t:sources.kind} odaberite {t:sources.kind.ldap}.
2. Upišite {t:sources.field.url} (`ldaps://…`, ili `ldap://…` uz uključen {t:sources.field.starttls}), {t:sources.field.bind_dn}, {t:sources.field.password} i {t:sources.field.base_dn}.
3. Uključite {t:sources.field.sign_in} ako se korisnici prijavljuju lozinkom iz imenika.
4. Pod {t:sources.field.every} odredite koliko se često imenik čita.
5. Pod {t:sources.advanced} po potrebi upišite {t:sources.field.user_filter}, {t:sources.field.group_base_dn}, {t:sources.field.group_filter}, {t:sources.field.email_attribute} i {t:sources.field.ca}.
6. Pritisnite {t:tree.create}. Ponistra se odmah spaja na imenik i javlja ako ne uspije.

### Imenik SCIM

1. Pritisnite {t:sources.new}, pod {t:sources.kind} odaberite {t:sources.kind.scim} i pritisnite {t:tree.create}.
2. Kopirajte {t:sources.here.scim_url} i {t:sources.token} i upišite ih kod izdavatelja (na primjer u dodjelu korisnika aplikaciji). Token se prikazuje samo tada.
3. Novi token izdajete u izborniku radnji uz izvor, {t:sources.renew}, pa potvrdite u dijalogu {t:sources.renewTitle}

### Popis izvora

1. Svaki izvor u popisu pokazuje naziv, vrstu, {t:sources.off} kad je isključen, {t:sources.synced} s vremenom zadnjeg čitanja i broj korisnika ({t:sources.people}). Ispod je posljednja greška, ako je ima.
2. U izborniku radnji: {t:sources.edit}, {t:sources.sync} (imenik LDAP i SAML s adresom metapodataka), {t:sources.renew} (SCIM) i {t:sources.delete}, koje traži potvrdu u dijalogu {t:sources.deleteTitle}

## Kako radi

Korisnik se kod izdavatelja prijavi gumbom s nazivom izvora na stranici prijave. Ponistra ga prvi put prepoznaje po potvrđenoj adresi e-pošte, a otad po identifikatoru koji mu je dao izdavatelj, pa promjena adrese kod izdavatelja ne mijenja račun. Kad su navedene {t:sources.domains}, prihvaćaju se samo adrese iz tih domena. Uz {t:sources.creates} osoba bez računa dobiva novi; inače račun prvo izrađuje administrator. Izdavatelj koji stvara račune mora imati domene, inače bi račun dobio svatko s računom kod javnog izdavatelja.

Za OpenID Connect Ponistra opis izdavatelja čita s adrese izdavatelja kad spremate postavke i potom jednom dnevno. Metapodatke SAML-a s adrese čita jednom dnevno i odmah na {t:sources.sync}; zalijepljeni metapodaci vrijede dok ih ne zamijenite. Prijava mora završiti u pregledniku u kojem je počela i unutar 10 minuta, a svaki odgovor izdavatelja vrijedi jednom. Tajna klijenta i lozinka imenika čuvaju se šifrirane i više se ne prikazuju; polje tada pokazuje {t:sources.keepSecret}, a metapodaci {t:sources.keepMetadata}.

Imenik LDAP čita se svakih 60 minuta, ili koliko odredite između 5 i 1440, i odmah nakon spremanja. Imenik SCIM sam šalje promjene čim nastanu. Korisnik koji dolazi iz imenika ima adresu e-pošte, ime, lozinku i aktivnost kakve su u imeniku: u dijalogu {t:users.edit} ta su polja onemogućena, a uz ime u popisu korisnika piše naziv izvora. Korisnik isključen u imeniku (u Active Directoryju onemogućen račun) deaktivira se i odjavljuje sa svih uređaja, kao i korisnik kojeg imenik više ne navodi. Njegov račun i dokumenti ostaju dok ga administrator ne izbriše.

Uz {t:sources.field.sign_in} korisnici imenika prijavljuju se na stranici prijave svojom adresom i lozinkom iz imenika, koju Ponistra provjerava kod imenika pri svakoj prijavi i nikad ne sprema. Vlastita lozinka u Ponistri tim korisnicima prestaje vrijediti, osim administratorima, koji tako mogu ući i kad imenik nije dostupan.

Uz {t:sources.groups} grupe dolaze od izvora: postojeća grupa istog naziva preuzima se, a grupa čiji je naziv zauzet dobiva naziv izvora u zagradi. Takva grupa ne može se preimenovati ni obrisati, a članstvo u njoj određuje izvor. Grupa koju izvor više nema uklanja se, osim ako bi nešto ostalo bez vlasnika; tada ostaje kao grupa instalacije.

Kad uklonite izvor, korisnici i grupe koje je donio ostaju kao vlastiti računi i grupe instalacije. Dodavanje, promjena i uklanjanje izvora te novi token upisuju se u [dnevnik](help:admin/journal), kao i prijave kod izdavatelja.

## Ograničenja

- Pravilo o pristupnom ključu ne odnosi se na prijavu kod izdavatelja; dodatnu provjeru (na primjer drugi faktor) tada određuje izdavatelj.
- Šifrirane SAML izjave (EncryptedAssertion) ne prihvaćaju se. Izdavatelj mora potpisivati odgovor ili izjavu.
- Imenik LDAP mora biti spojen šifrirano: {t:error.unencrypted_directory}
- Ugniježđene grupe imenika LDAP ne razmotavaju se: član je samo onaj koga grupa navodi izravno.
- Posljednji aktivni administrator ne deaktivira se, čak ni kad ga imenik isključi.
- Bez domena izvor koji stvara račune ne može se spremiti: {t:error.domains_required}
- Uključen izvor bez tajne ili metapodataka ne sprema se: {t:error.secret_required} {t:error.metadata_required}
- Kad izdavatelj ili imenik nije dostupan ili odbije spajanje, pri spremanju i ispod izvora u popisu piše jedno od ovoga, pa provjerite adresu, račun za povezivanje i lozinku: {t:error.provider_unreachable} {t:error.directory_unreachable} {t:error.directory_refused}
- Ako je adresa izdavatelja u njegovu opisu drukčija od upisane, piše {t:error.provider_mismatch}
- Dodavanje, promjena i uklanjanje izvora te novi token mogu tražiti potvrdu da ste to vi.

## Povezano

- [Korisnici](help:admin/users)
- [Grupe](help:admin/groups)
- [Prijava i način prijave](help:account/sign-in)
- [Dnevnik](help:admin/journal)
