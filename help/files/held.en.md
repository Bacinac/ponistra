# File content by kind

Archives, mail messages, contacts, calendars, Markdown and pictures a browser does not show by itself open to show what they hold rather than as a stream of bytes.

## How to use it

1. In a folder, press the file. The file's page shows its content.
2. An archive's entry or a message's attachment is saved by pressing its name.
3. When an archive is protected by a password, the page says {t:shown.locked} Type the password into the {t:shown.password} field and press {t:shown.open}.
4. The {t:file.download} button always saves the whole file as it was uploaded.
5. Above the contacts, press {t:shown.toContacts}. Below the button it says how many contacts were added and how many completed, with the link {t:shown.openContacts}.
6. Above the events, press {t:shown.toCalendar} and choose one of your calendars or {t:shown.newCalendar}. Below the button it says how many events were added and how many updated, with the link {t:shown.openCalendar}.
7. Above an archive's list, press {t:shown.unpack}. When unpacking ends, a new folder with the archive's content opens.

The same content, shortened, is shown by the [item preview](help:documents/preview) beside a folder's list.

## How it works

The kind is told by the file's bytes, not by its extension.

- An archive (ZIP, 7z, RAR, TAR, GZip, BZip2, XZ, Zstandard, LZ4, ISO, CAB, LHA, XAR) shows the list of its folders and files with their size and date of change. An empty archive says {t:shown.emptyArchive}
- A mail message (EML, MHT and Outlook's MSG) shows {t:mail.from}, {t:mail.to}, {t:mail.cc}, {t:mail.date}, the attachments and the body. Pictures carried in an EML message are shown; outside pictures and scripts are not loaded.
- Contacts (VCF) are shown as a list of people with their addresses, telephones and photo. A file without contacts says {t:shown.noPeople}
- A calendar (ICS) shows its events by time, with place and organiser. An event lasting the whole day is marked {t:calendar.allDay}, one that repeats {t:shown.repeats}. A file without events says {t:shown.noEvents}
- Markdown is shown formatted, with headings, lists and tables.
- BMP, ICO, TIFF and PSD pictures are shown as PNG. A TIFF also goes through [text recognition](help:pdf/ocr): once it is over, it is shown as a PDF with all its pages and can be searched.

{t:shown.toContacts} adds each person in the file to your [contacts](help:contacts/overview). A person you already have, by the same card identifier, email address, telephone or name, is not doubled: they only get what they lack. Contact groups in the file are skipped.

{t:shown.toCalendar} writes the events into the chosen calendar, with their repetition, place, organizer and attendees as the file gives them. No invitations are sent to anyone. An event the calendar already has, by the same identifier, is replaced by the one in the file, so adding the same file again does not double the events. {t:shown.newCalendar} makes a calendar named as the file names itself, else after the file's name.

{t:shown.unpack} runs in the background. The new folder takes the archive's name and is made beside the archive where you may edit that folder, else at the top of your documents. The archive's folders become folders and its files are placed as if uploaded: Word, Excel and PowerPoint files become Ponistra documents, and the date of change stays the one in the archive. A protected archive's password is used for that unpacking only and is deleted as soon as it ends.

An archive's password is kept nowhere. It holds only for that view, so it is typed again each time the file is opened. Every entry or attachment saved is noted in the access log, as saving the whole file is.

## Limits

- An archive is shown up to the size of the largest file the installation accepts (10 GiB by default) and with at most 10,000 entries.
- The item preview shows an archive's first 50 entries, the file's page all of them.
- When the password is wrong, the page says {t:error.archive_locked} Type the right password.
- In a {t:confined.label} folder, entries and attachments cannot be saved, and contacts and events cannot be added, as they would leave the folder. Unpacking is allowed.
- Unpacking takes the archive's first 10,000 entries. What was unpacked before an error stays in the new folder. When the server runs out of room, unpacking stops with the message {t:error.no_room}
- To a visitor without an account, {t:shown.toContacts}, {t:shown.toCalendar} and {t:shown.unpack} are not offered, nor on a file on the network or in Projects.

## Related

- [Files](help:files/overview)
- [Item preview](help:documents/preview)
- [Text recognition](help:pdf/ocr)
