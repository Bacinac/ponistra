# Pravila prijave i dijeljenja

Administrator određuje kome je pristupni ključ obavezan za prijavu i tko smije izraditi poveznicu za nekoga izvan instalacije.

## Kako se koristi

1. Na stranici {t:users.title}, u odjeljku {t:policy.title}, pod {t:policy.passkeys} odaberite {t:policy.passkeys.nobody}, {t:policy.passkeys.administrators} ili {t:policy.passkeys.everyone}.
2. U odjeljku {t:policy.outside.title}, pod {t:policy.outside}, odaberite {t:policy.outside.nobody}, {t:policy.outside.administrators} ili {t:policy.outside.everyone}.

## Kako radi

Pravilo o pristupnom ključu vrijedi od sljedeće prijave. Tko mora imati pristupni ključ, lozinkom se prijavljuje samo dok ga ne doda, a nakon toga samo ključem. Korisnik bez ključa nakon prijave lozinkom najprije dodaje ključ.

Ako takav korisnik izgubi uređaj, administrator mu pod {t:users.edit} postavlja novu lozinku; time se brišu njegovi pristupni ključevi, a novi dodaje pri sljedećoj prijavi.

Pravilo dijeljenja određuje tko smije izraditi poveznicu kojom netko bez računa u instalaciji otvara ploču. Uz {t:policy.outside.nobody} prestaju vrijediti i sve već izrađene poveznice.

Svaka promjena pravila upisuje se u [dnevnik](help:admin/journal).

## Ograničenja

- Promjena pravila može tražiti potvrdu da ste to vi.
- Korisnik kojemu je ključ obavezan ne može obrisati svoj posljednji pristupni ključ.

## Povezano

- [Korisnici](help:admin/users)
