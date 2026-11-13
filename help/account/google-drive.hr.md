# Preuzimanje Google Drivea

Preuzima vaš Google Drive i dijeljene diskove koje vidite u Ponistru i prati ih dok Google ne napustite.

## Kako se koristi

1. Povežite svoj Google račun u poštu preko Googlea ([Računi e-pošte](help:mail/accounts)). Ako je
   račun povezan prije nego što je Ponistra tražila pristup Driveu, pritisnite
   {t:mail.oauthAgain.google}.
2. Otvorite [Postavke](/settings/google), pa {t:drive.title} pod {t:settings.leaving}.
3. Uz adresu računa pritisnite {t:drive.begin}. Dok traje kopiranje, stoji {t:drive.copying} s
   brojem preuzetih datoteka.
4. Kad je kopija gotova, stoji {t:drive.ready} s vremenom zadnjeg prolaza. Ispod su mape koje su
   nastale: vaš Drive kao mapa Google Drive na vrhu vaših dokumenata i svaki dijeljeni disk kao mapa
   svog imena. Uz svaku piše koliko datoteka, mapa i prostora drži.
5. {t:drive.refresh} preuzima promjene odmah, bez čekanja sljedećeg prolaza.
6. Kad ste spremni napustiti Google, pritisnite {t:drive.finish} i potvrdite u prozoru
   {t:drive.finishTitle} Dok se zadnje promjene preuzimaju, stoji {t:drive.finishing}
7. Želite li sve preuzeto ukloniti, pritisnite {t:drive.stop} i potvrdite u prozoru
   {t:drive.stopTitle}

## Kako radi

- Formati: Google dokumenti, tablice i prezentacije preuzimaju se kao Word, Excel i PowerPoint
  i uvoze kao dokumenti Ponistre; Google crteži kao PDF. Sve ostalo preuzima se kao datoteka kakva
  jest, a Office datoteke uvoze se kao kod učitavanja.
- Mape i prava: mape ostaju kako su u Googleu. Kome je u Googleu nešto podijeljeno, a korisnik
  je ove instalacije, dobiva isto pravo u Ponistri: vlasnik i organizator posjeduju, urednik i
  organizator datoteka uređuju, komentator i čitatelj čitaju. Pravo se daje na mapi ili datoteci
  samo kad je šire od onog što daje mapa iznad. Osobe izvan instalacije, grupe i poveznice ne
  prenose se.
- Samo promjene: prvi prolaz čita sve. Svaki sljedeći, svakih 5 minuta, uzima samo ono što je
  Google javio kao promijenjeno: nove i izmijenjene datoteke preuzima ponovno, preimenovane i
  premještene samo premješta, obrisane i one u smeću uklanja. Ponovno uvezen dokument zadržava svoje
  mjesto i verzije.
- Samo za čitanje: dok Google ostaje izvornik, preuzete mape u Ponistri samo se čitaju, svima.
  {t:drive.finishWarning}
- Dijeljeni disk preuzima se jednom za cijelu instalaciju: prati ga prvi član koji ga je
  preuzeo, a ostali ga članovi dobivaju kroz prava. Odustane li on, disk preuzima sljedeći član koji
  ga vidi.
- Odustajanje: {t:drive.stopWarning}
- Što ostaje izvan: pod {t:drive.left} navedeno je ono što se nije moglo preuzeti, uz razlog:
  {t:drive.why.shortcut}, {t:drive.why.google_only} (obrasci, web-mjesta, karte),
  {t:drive.why.no_download} ili {t:drive.why.too_large}. Pod {t:drive.kept} su Office datoteke koje
  uvoz nije mogao pročitati, pa su preuzete kao datoteke.

## Ograničenja

- Pošta, kalendar i kontakti ne preuzimaju se ovdje, nego kroz povezani račun pošte.
- Bez računa povezanog preko Googlea stoji {t:drive.none} Ako administrator nije postavio prijavu
  preko Googlea, preuzimanje se ne može započeti.
- Ako Google javi da račun nije dopustio čitanje Drivea, ili da je prijava istekla, preuzimanje
  staje: pritisnite {t:mail.oauthAgain.google}, pa po povratku {t:drive.retry}.
- Ako Drive API nije uključen u Googleovu projektu instalacije, to mora uključiti administrator.
- Komentari i povijest verzija iz Googlea ne prenose se.

## Povezano

- [Računi e-pošte](help:mail/accounts)
- [Mape i datoteke](help:files/overview)
