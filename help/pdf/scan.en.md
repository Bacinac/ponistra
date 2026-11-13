# Scanning

Ponistra straightens pages of paper photographed with a phone and saves them as one PDF with its text recognised, in a folder or as a mail's attachment.

## How to use it

### Into a folder

1. Open a folder, press {t:create.new} and choose {t:create.scan}
2. On a phone press {t:scan.take}: the camera opens and takes one page. On a computer, or for photos you already have, press {t:scan.add}
3. Ponistra finds the page's edges and outlines them on the photo. Where an edge is wrong, drag the corner to the right place. With a keyboard, reach a corner with Tab and move it with the arrow keys.
4. {t:scan.whole} takes the whole photo, without cropping.
5. Repeat for each following page. The thumbnails below the photo show the pages in order: pressing a thumbnail opens that page, and {t:scan.remove} takes it out.
6. The name in {t:tree.name} starts as today's date; change it as you like.
7. Press {t:scan.save}. The new PDF file opens when it is ready.

### As a mail's attachment

1. In the message you are writing, press {t:mail.scan}
2. Take the pages as above and press {t:scan.attach}. The PDF is added among the message's attachments, named as in {t:tree.name}.

## How it works

Each photo is uploaded to the server as soon as it is taken or added, and a spinner turns on it while its edges are found. The page's edge is looked for as the largest bright area of the photo, so paper is found best on a dark surface.

Saving straightens each page by its corners and evens out the paper to white, so that shadows and uneven light disappear. Colours on the page stay. The pages go into the PDF in the order they were taken, and the longer side of each page is as long as an A4 page's, as a photo does not show how large the paper is. The text is then recognised in Croatian and English, so the PDF is searchable at once. While the PDF is made, {t:job.scan} is shown.

A PDF in a folder is seen by everyone who sees the folder. The photos are not kept: those that did not become a PDF are deleted by themselves after an hour.

## Limits

- A PDF holds at most 100 pages.
- A photo must be JPEG, PNG or WebP. A phone's camera takes JPEG.
- Saving into a folder needs the right to edit the folder; without it {t:create.scan} is disabled.
- {t:error.invalid_corners} The corners may not cross or squeeze into too small an area; drag them back to the page's edges.
- {t:error.unknown_file} Shown when more than an hour has passed since the page was taken; take it again.
- {t:error.unreadable} Shown for a photo that cannot be opened; take it again.

## Related

- [Text recognition](help:pdf/ocr)
- [PDF files](help:pdf/viewer)
- [Writing a message](help:mail/composing)
