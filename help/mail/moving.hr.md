# Selidba pošte između računa

Poštu koju je jedan račun donio Ponistra prenosi u drugi račun kod njegova pružatelja, primjerice kad organizacija prelazi s jednog pružatelja pošte na drugi.

## Kako se koristi

1. Povežite oba računa: onaj s kojega se poruke sele i onaj u koji se sele.
2. Na stranici pošte dugo pritisnite ili desnom tipkom kliknite račun s kojega selite.
3. Odaberite {t:mail.moveMailItem} Ta je stavka ponuđena kad imate barem jedan drugi račun povezan preko IMAP-a.
4. U dijalogu {t:mail.moveMail} pod {t:mail.moveMailTo} odaberite odredišni račun.
5. Pritisnite {t:mail.moveMailStart}. Dijalog možete zatvoriti; selidba se nastavlja kao posao {t:job.mailMove}, a njezin tijek stoji u donjem desnom kutu.
6. Kad završi, dijalog kaže koliko je poruka premješteno.

## Kako radi

Ponistra šalje svaku poruku u izvornom obliku, s oznakama pročitano, omiljeno i odgovoreno te izvornim datumom. Poruke iz pristigle pošte, poslane pošte i arhive idu u odgovarajuće mape odredišnog računa, a ako ih on nema, Ponistra ih napravi. Poruke iz vlastitih mapa računa idu u mape istog imena odredišnog računa, koje se naprave gdje ih nema, i u Ponistri se premjeste pod odredišni račun. Vaše vlastite mape u Ponistri zadržavaju svoje poruke.

Premještena poruka od tada pripada odredišnom računu: nosi njegovu boju, a odgovor na nju odlazi s njega. Selidba radi na poslužitelju i kad je preglednik zatvoren. Prekine li je ponovno pokretanje poslužitelja, nastavlja se ondje gdje je stala; isto vrijedi ako je ponovno pokrenete. Na izvornom računu ništa se ne briše.

## Ograničenja

- Smeće, neželjena pošta i skice ostaju na izvornom računu.
- Poruke koje odredišni račun već ima ne šalju se ponovno.
- Odredište mora biti račun povezan preko IMAP-a (lozinkom, Googleom ili Microsoftom). Račun povezan preko ActiveSynca može biti samo izvor.
- Prekid točno između slanja poruke i bilježenja može ostaviti jednu poruku dvaput kod odredišnog pružatelja; u Ponistri je i tada jedna.
- Ako odredišni poslužitelj odbije prijavu ili prekine vezu, selidba staje uz poruku o grešci; pokrenite je ponovno kad je račun opet ispravan.
- Selidbu u zajedničkom sandučiću pokreće njegov vlasnik.

## Povezano

- [Računi pošte](help:mail/accounts)
- [Zajednički sandučići](help:mail/mailboxes)
