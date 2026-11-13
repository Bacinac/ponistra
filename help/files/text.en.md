# Text files

A text file, such as a log, a configuration or source code, is shown read-only, with line numbers, syntax highlighting and search.

## How to use it

### Search

1. Open the file, click in the text and press {k:Mod-f}. The {t:text.find} field opens above the text.
2. Type what you are looking for and press {k:Enter} for the next match.
3. The {t:text.next} and {t:text.previous} buttons move between matches, and {t:text.all} selects them all. {k:F3} and {k:Shift-F3} do the same.
4. Turn on {t:text.matchCase}, {t:text.regexp} or {t:text.byWord} when you need a narrower search.
5. {t:text.close} or {k:Escape} closes the search.

### Going to a line

1. Press {k:Mod-Alt-g}.
2. In the {t:text.goToLine} field, type the line number and press {t:text.go}.

## How it works

Syntax colours are chosen by the file name's extension, so `.py`, `.js` or `.json` files, for example, are shown highlighted. The bottom line gives the character encoding the text was read in.

The text can be selected and copied, but not changed.

## Limits

- At most the first 5 MB of a file are shown. When the file is larger, the bottom line says so, and the whole file is had by downloading it.
- The file cannot be edited in Ponistra.

## Related

- [Files](help:files/overview)
