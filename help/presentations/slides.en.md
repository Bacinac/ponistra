# Slides

Any document can be shown as a presentation: headings divide a tab's text into slides, and a slide's layout decides where each part of the text stands.

## How to use it

### The Slides view

1. On the right of the toolbar choose {t:view.label}, then {t:view.slides}.
2. Write as in text. A new slide starts with each {t:command.title}, each {t:command.heading1} and each {t:command.slideBreak} from the {t:editor.insert} menu.
3. The layout's empty places remind you what goes in them, for example a title or text.

### Layout and size

1. Stand in a slide and on the toolbar, under {t:commandGroup.slideLayout}, choose {t:slides.layout.auto}, {t:slides.layout.title}, {t:slides.layout.content}, {t:slides.layout.section}, {t:slides.layout.two}, {t:slides.layout.titleOnly} or {t:slides.layout.blank}.
2. Under {t:commandGroup.slideSize} choose {t:command.slideSize.wide} or {t:command.slideSize.standard}.
3. {t:command.hideSlide} hides the slide from the show. Above a hidden slide stands {t:slides.hidden}.

### Speaker notes

1. In the {t:editor.insert} menu choose {t:command.speakerNotes}. The notes open at the end of the slide you are in.
2. {k:Enter} in an empty line of the notes takes you back to the slide.

## How it works

{t:slides.layout.auto} picks the layout by the slide's content: a slide that starts with the document's title is {t:slides.layout.title}, a slide with a {t:command.columnBreak} is {t:slides.layout.two}, and a slide that starts with a level 1 heading is {t:slides.layout.content} when there is text under the heading, and otherwise {t:slides.layout.section}. The text before the first heading is a slide of its own when it is not empty.

When you change the layout, no text is lost: a part the new layout has no place for goes where the built-in layout of the same kind would put it. A presentation uploaded from PowerPoint keeps its template, so the layouts are offered under the template's names. A slide PowerPoint gave a background of its own shows it instead of its layout's, and keeps it when the document is saved as PowerPoint.

Slides are numbered through all the document's tabs.

## Limits

- Only someone who may edit the document changes the layout, the size and hiding.
- Speaker notes cannot be added from a table, a header, a footer or a note.

## Related

- [Presenting](help:presentations/show)
- [The document editor](help:text/overview)
- [Saving to a file](help:text/export)
