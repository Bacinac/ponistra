# Editing an image

A PNG, JPEG, WebP or AVIF image can be cropped, turned, made smaller, toned and marked, while the original file stays as it is.

## How to use it

### Edits

1. Open the image and press {t:image.edit}. The {t:image.editing} panel opens.
2. Under {t:image.cropping}, press {t:image.crop} and adjust the frame on the image. Under {t:image.ratio} you choose {t:image.ratio.free}, 1:1, 4:3 or 16:9, and {t:image.uncrop} brings back the whole image.
3. Under {t:image.turn} are {t:pages.turnLeft}, {t:pages.turnRight}, {t:image.flipAcross} and {t:image.flipDown}.
4. Under {t:explorer.size} you choose the image's longest side: {t:image.side.original} or one of the smaller ones. Below the choice is the size of the copy in pixels.
5. Under {t:image.tone} the sliders change {t:image.brightness}, {t:image.contrast} and {t:image.saturation}.

### Marks

1. Under {t:image.marks} choose {t:image.mark.arrow}, {t:image.mark.rectangle}, {t:image.mark.stroke}, {t:image.mark.text} or {t:image.mark.blur}.
2. Drag across the image. For text, press a place on the image, type the text and press {k:Enter}.
3. For every mark except the blur you choose a colour and a width.
4. Press a mark to select it. The {t:pdf.remove} button or the {k:Delete} key removes it, and {k:Escape} leaves the tool.

### A new image

1. Press {t:image.saveAs}
2. In the {t:image.saveAs.heading} dialog, keep or change the name. The suggested name is the image's own with "(edited)" added.
3. The new image is saved beside this one and opens at once.

## How it works

Edits and marks do not change the file: they are kept beside it and drawn each time the image is opened. Everyone who has the image open sees them at once. {t:command.undo} and {t:command.redo} ({k:Mod-z} and {k:Mod-y}) take your steps back and forth, and {t:image.reset} removes all edits and marks at once.

A downloaded image, and one opened in a new tab, carry the edits and marks, in the same format as the original. A new image from {t:image.saveAs} becomes a file of its own, while the original keeps its edits as they are.

## Limits

- Only someone who may edit the image sees {t:image.edit}.
- Other kinds of image are shown but cannot be edited.
- An image that cannot be read is not shown; the page reports: {t:image.unreadable}
- When you may not add to the image's folder, the new image is saved among your own documents.

## Related

- [Files](help:files/overview)
- [Pictures and PDF in a document](help:text/images)
