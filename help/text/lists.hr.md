# Popisi

Odlomke pretvarate u popis s grafičkim oznakama, numerirani popis ili kontrolni popis s kvačicama, s razinama i vlastitim oblikom oznaka.

## Kako se koristi

### Izrada popisa

1. Stanite u odlomak ili odaberite više njih.
2. Na traci alata pritisnite {t:command.bulletList} ({k:Shift-Mod-8}), {t:command.numberList} ({k:Shift-Mod-7}) ili {t:command.checkList} ({k:Shift-Mod-9}).
3. Isto postižete tipkanjem na početku retka: „- ” za oznake, „1. ” za brojeve, „[] ” za kvačice.
4. {k:Tab} spušta stavku razinu niže, a {k:Shift-Tab} je vraća. Isto rade {t:command.indentMore} ({k:Mod-m}) i {t:command.indentLess} ({k:Shift-Mod-m}).

### Oblik oznaka

1. Stanite u popis i otvorite {t:editor.listForm} na traci alata.
2. Odaberite gotovi oblik: {t:command.bulletForm} za popis s oznakama, {t:command.numberForm} za numerirani.
3. U istom izborniku {t:command.numberRestart} počinje brojati iznova od te stavke, a {t:command.numberContinue} nastavlja brojanje prethodnog popisa.

### Vlastiti oblik

1. U izborniku {t:editor.listForm} odaberite {t:command.listFormat} Otvara se dijalog {t:listFormat.title}.
2. Lijevo odaberite razinu ({t:listFormat.level}).
3. Pod {t:listFormat.kind} odaberite {t:listFormat.number} ili {t:listFormat.bullet}.
4. Za brojeve odaberite {t:listFormat.numbering}, tekst {t:listFormat.prefix} i {t:listFormat.suffix} te po želji {t:listFormat.nested}. Za oznake upišite {t:listFormat.symbol} ili ga odaberite među {t:listFormat.symbols}.
5. Provjerite {t:listFormat.preview} i pritisnite {t:styles.apply}.

## Kako radi

Oblik vrijedi za cijeli popis kojem stavka pripada, za svaku razinu zasebno.

{k:Enter} u praznoj stavci vraća je razinu više, a na prvoj razini završava popis, a {k:Backspace} na početku stavke uklanja njezinu oznaku. Kvačicu u kontrolnom popisu označavate pritiskom na nju.

## Ograničenja

- Svaka razina s grafičkom oznakom mora imati znak.
- Brojevi naslova ne određuju se ovdje, nego u [stilovima](help:text/styles).

## Povezano

- [Stilovi i tema](help:text/styles)
- [Ravnalo i tabulatori](help:text/ruler)
- [Oblikovanje teksta](help:text/formatting)
