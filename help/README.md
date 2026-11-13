# Writing the help

The help is part of the code: articles in this folder ship with each release, and
`scripts/help.py` holds a push until they are whole and current. Every article has the same shape
and the same depth, whoever writes it. This file is the only rule book for it.

## Files

An article is three files in its section's folder, its id being `<section>/<slug>`:

| File | Holds |
|---|---|
| `<slug>.json` | its record (below) |
| `<slug>.hr.md` | the Croatian text |
| `<slug>.en.md` | the English text, the same article |

```json
{
  "order": 10,
  "audience": "everyone",
  "covers": ["route:/mail/:folder/:message"],
  "quiet": ["mail.loading"],
  "describes": { "frontend/src/mail.tsx#MessageView": "", "backend/apps/mail/views.py#snooze": "" }
}
```

- `order`: its place in the section, in tens.
- `audience`: `everyone` or `admin`. An administrator's article never loads for anyone else; one for
  everyone cannot link to it.
- `covers`: what of the structure this article explains, from `scripts/help.sh gaps`:
  `route:` (the screen F1 opens this article from; one article per route), `setting:`, `action:`,
  `tool:`.
- `quiet`: interface strings of this article's screens that need no mention of their own (a title
  repeated, an aria label, a string that takes values). Exact keys, no patterns. Every string the
  user meets as a function or a choice is named in the text instead; `quiet` is not a way around it.
- `describes`: the code the text makes promises about, as `path#TopLevelName` (or `path` alone only
  for a short file). List what decides the behaviour: the component, the view, the sync. Leave the
  values empty and run `scripts/help.sh seen <id>`, which fills them.

## The text

Both languages have this exact skeleton; the gate compares them:

```markdown
# Title, the function's name as a noun

One sentence on what it does and what it is for. It is the snippet the search shows.

## Kako se koristi        (How to use it)
## Kako radi              (How it works)
## Ograničenja            (Limits)
## Povezano               (Related)
```

**Kako se koristi**: numbered steps from where the user is standing, one action per step, every
way of reaching the function (menu, long press, shortcut, search box, phone). A `###` per variant
when there are several.

**Kako radi**: what happens that the screen does not show. What is saved and where, who else sees
it, what reaches the mail server or other devices, what happens offline, in a shared document, on
the phone, what a stated default is. Written by reading the code, never by guessing from the label.

**Ograničenja**: what it does not do, the rights it needs, what each of its error messages means and
what to do about it. If there truly are none, say so in a sentence, having checked.

**Povezano**: a list of links to the articles a reader goes to next, at least one.

### Marks

| Write | For | Becomes |
|---|---|---|
| `{t:mail.snooze}` | an interface name, always | the string in the reader's language, bold |
| `{k:Mod-/}` | a shortcut, `Mod` being Ctrl or ⌘ | Ctrl+/ or ⌘/ by the reader's device |
| `[text](help:mail/reading)` | another article | |
| `[text](/mail)` | a screen of the application | |
| `![what it shows](shot:mail-list)` | a picture, made by a shot in `e2e/shots/` | the reader's language and theme |

Never retype an interface name: it goes stale silently when the name changes. Bold is reserved for
`{t:…}`, and the gate refuses any other. A string that takes values (`{n}`) cannot be named; list it
under `quiet` and describe it in words.

### Style and depth

- Formal Croatian, `vi` in lower case as the interface writes it, in the user's words: "fotografije", "korisnik". Not "klikni" but
  "pritisnite". Ponistra declines as a feminine noun (Ponistre, u Ponistri, za Ponistru, s Ponistrom).
- Written for anyone at any installation: no names, addresses or habits of a particular one.
- No marketing, no comparison with other products, no history of the feature. Plain statements.
- No em dashes. Numbers as digits.
- One function an article. Split when a heading would need a second "how to use it". Each article
  stands alone; link instead of repeating.
- Depth is set by the strings: a screen's every function, choice and message ends up either named in
  an article or deliberately `quiet`. An article of a few lines over a screen with thirty strings is
  not finished. Read `help/mail/` as the measure of how far to go.
- A picture for a screen the reader must find their way around, not for every step.

## The gate

```sh
scripts/help.sh gaps label:mail.   # what no article covers yet under a prefix, with its text
scripts/help.sh check              # what a push checks
scripts/help.sh seen mail/reading  # after reading the article against changed code
scripts/help.sh sync               # takes what is now covered out of uncovered.txt
```

- `ignored.txt`: what never needs help, one pattern a line, with the reason after `#`.
- `uncovered.txt`: what has not been written yet, shrinking to nothing, when the file goes. Anything
  new that is not on it fails the push, so nothing arrives without a place in the help.

**When code changes.** A changed interface string is new text only where it is named, and changes
by itself. New behaviour fails the push through `describes`, or through a new string or route with
no place: read the article against the change, correct what no longer holds and only then run
`seen`. `seen` is a statement that the text was read and holds; it is not a way past the gate.

## Pictures

`e2e/shots/<section>.ts` makes them, each named once:

```ts
shot('mail-list', async (page) => {
  await page.goto('/mail');
});
```

What `make` returns (a locator) is what is taken, the whole window if nothing. The accounts it opens
are filled by `backend/apps/help/seeds/<section>.py`, which writes each text in the account's language.
Each runs for both languages and both themes, every night, and a release carries the latest. A shot
that fails is reported by the night's run.
