# Presenting

Presenting shows the document's slides over the whole screen, and the presenter view in another window shows the notes, the next slide and the time.

## How to use it

### Starting

1. Click the document's title in the path and in the menu choose {t:command.presentStart} or {t:command.present}. With the right to edit, the same buttons are also on the toolbar in the {t:view.slides} view.
2. A click or {k:ArrowRight} takes you to the next slide, and {k:ArrowLeft} to the one before. {k:Home} and {k:End} take you to the first and last slide.
3. Type a slide's number and press {k:Enter} to jump to that slide.
4. {k:Escape} or {t:show.end} ends the show.

### Presenter view

1. Move the mouse: at the bottom of the screen appear {t:show.previous}, {t:show.next}, {t:show.presenter} and {t:show.end}, and when the show does not take the whole screen also {t:show.fullScreen}.
2. Press {t:show.presenter}. A separate window opens, which you can move to another screen.
3. In it are the {t:show.current}, the next slide, the {t:command.speakerNotes}, the {t:show.elapsed} and the {t:show.clock}.
4. {t:show.pause}, {t:show.resume} and {t:show.restart} control the timing. {t:show.previous} and {t:show.next} move the show.

## How it works

The show goes through the slides of all tabs in order and skips hidden slides, except when you reach a hidden slide by typing its number. After the last slide comes a closing screen; the next click ends the show. When you leave full screen, the show ends.

The presenter view and the show run in the same browser and follow each other: a move in one window moves the other too. The presenter view shows {t:show.slide} with the current slide's number and the total of slides, and after the last one {t:show.over}.

## Limits

- The browser must allow pop-up windows for Ponistra for the presenter view to open.
- The presenter view cannot be opened on another device.

## Related

- [Slides](help:presentations/slides)
- [Printing](help:text/print)
