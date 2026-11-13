# Smeće

Stavke koje bacite u smeće ostaju ondje dok ih ne vratite ili trajno ne obrišete, zajedno sa svime što sadrže.

## Kako se koristi

### Bacanje u smeće

1. U izborniku stavke odaberite {t:tree.toTrash} ili odaberite stavke i pritisnite {k:Delete}.
2. Stavku možete i povući na {t:trash.title} u lijevom stupcu.

### Vraćanje i trajno brisanje

1. U lijevom stupcu modula {t:rail.documents} pritisnite {t:trash.title}.
2. Uz stavku pritisnite {t:trash.restore} da se vrati na svoje mjesto. Iste radnje nudi desni klik na redak.
3. Pritisnite {t:trash.purge} i potvrdite u dijalogu {t:trash.purgeTitle}
4. Za više stavki odjednom odaberite ih kvačicama i radnju pokrenite na traci iznad popisa.

## Kako radi

Smeće prikazuje stavke koje smijete uređivati, posljednje bačene prve, s datumom bacanja. Mapa u smeću nosi sa sobom sve što sadrži, pa je ono i vraćeno i obrisano zajedno s njom.

Vraćena stavka vraća se u mapu iz koje je bačena. Ako je ta mapa i sama u smeću ili više ne postoji, stavka se vraća na najvišu razinu i zadržava svoje vlasnike.

Smeće se ne prazni samo: stavke ostaju u njemu dok ih netko ne vrati ili trajno ne obriše. Prazno smeće prikazuje: {t:trash.empty}

## Ograničenja

- U smeće baca i iz njega vraća samo onaj tko smije uređivati stavku.
- Trajno briše samo vlasnik stavke. Trajno brisanje ne može se poništiti.
- Stavka uz koju stoji lokot ne može se trajno izbrisati: oznaka {t:retention.kept.held} znači da je ona ili nešto u njoj pod zakonskim čuvanjem, a {t:retention.kept.retained} da je u roku čuvanja koji je postavio administrator.
- Mapu tvrtke ne možete baciti u smeće.

## Povezano

- [Rad sa stavkama](help:documents/organising)
- [Verzije](help:documents/versions)
- [Dijeljenje](help:documents/sharing)
