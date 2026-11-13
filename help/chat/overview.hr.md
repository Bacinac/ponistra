# Razgovori

Razgovori su kratke poruke među korisnicima instalacije: s jednim kolegom, u skupini ili u razgovoru sastanka.

## Kako se koristi

### Novi razgovor

1. Otvorite [razgovore](/chat) na traci s lijeve strane i pritisnite {t:chat.new}.
2. U polje {t:chat.people} upišite kolege.
3. Za skupinu po želji upišite {t:chat.groupTitle}.
4. Pritisnite {t:chat.start}. Razgovor se otvara.

### Popis razgovora

1. U lijevom stupcu, pod {t:chat.conversations}, razgovori su složeni po zadnjoj poruci, a uz svaki stoji ta poruka i broj nepročitanih.
2. Ispod popisa poveznica vodi na kontakte.

### Razgovor

- {t:meeting.now} u razgovoru otvara sastanak za taj razgovor i zvoni svima u njemu. U razgovoru sastanka na tom je mjestu {t:meeting.join}.
- {t:meeting.now} u kanalu otvara sastanak bez zvonjenja i objavljuje poruku {t:chat.meetingOpened} s gumbom {t:meeting.join}; tko se pridruži, postaje član kanala.
- Uz izravni razgovor točka i {t:chat.online} pokazuju da kolega ima otvorenu Ponistru, a u skupini zaglavlje kaže koliko ih je na mreži.
- {t:meeting.now} u zaglavlju stranice otvara novi sastanak bez razgovora.
- U izborniku skupine ili razgovora sastanka su {t:invite.add}, {t:tree.rename} (samo za skupinu, u prozoru {t:chat.renameGroup}) i {t:chat.leave}. Isti izbornik otvara se desnim klikom ili dugim pritiskom na razgovor u popisu.

## Kako radi

Razgovor između dvoje uvijek je jedan: novi razgovor s istim kolegom otvara onaj koji već imate. Razgovor s više kolega je skupina. Svaki sastanak ima svoj razgovor, koji ostaje i nakon sastanka; u njemu pišu i gosti sastanka.

Kad napustite razgovor, njegove poruke više ne vidite, a netko vas može ponovno dodati. Kad ga napusti posljednji član, razgovor nestaje, osim ako su mu poruke u roku čuvanja koji je postavio administrator. Razgovor između dvoje ne napušta se i ne dobiva nove članove.

Na širokom zaslonu stranica se otvara na razgovoru u kojem ste zadnji put bili. Dok nemate nijednog razgovora, popis to kaže, a razgovor bez poruka piše {t:chat.empty}

Za stalne teme i timove postoje [kanali](help:chat/channels), koji se ponašaju drukčije: otvoreni kanal ostaje i kad ga svi napuste, a javljaju se samo spominjanja i odgovori u nitima koje pratite.

## Ograničenja

- Razgovaraju samo korisnici instalacije i gosti sastanka; osobe izvan instalacije ne mogu se dodati u razgovor.

## Povezano

- [Kanali](help:chat/channels)
- [Poruke u razgovoru](help:chat/messages)
- [Reakcije](help:chat/reactions)
- [Sastanci](help:meetings/overview)
