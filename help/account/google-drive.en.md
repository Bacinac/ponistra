# Taking Google Drive

Takes your Google Drive and the shared drives you see into Ponistra and follows them until you leave Google.

## How to use it

1. Connect your Google account to your mail through Google ([Mail accounts](help:mail/accounts)). If
   the account was connected before Ponistra asked to read Drive, press
   {t:mail.oauthAgain.google}.
2. Open [Settings](/settings/google), then {t:drive.title} under {t:settings.documents}.
3. Beside the account's address press {t:drive.begin}. While copying, it shows {t:drive.copying}
   with the number of files taken.
4. Once the copy is done, it shows {t:drive.ready} with the time of the last pass. Below are the
   folders made: your Drive as the folder Google Drive at the top of your documents, and each shared
   drive as a folder of its name. Each says how many files and folders it holds and how much space.
5. {t:drive.refresh} takes the changes at once, without waiting for the next pass.
6. When you are ready to leave Google, press {t:drive.finish} and confirm in {t:drive.finishTitle}
   While the last changes are taken, it shows {t:drive.finishing}
7. To remove everything taken, press {t:drive.stop} and confirm in {t:drive.stopTitle}

## How it works

- Formats: Google Docs, Sheets and Slides are taken as Word, Excel and PowerPoint and imported
  as Ponistra documents; Google Drawings as PDF. Everything else is taken as the file it is, and
  Office files are imported as an upload imports them.
- Folders and rights: folders stay as they are at Google. Whoever a file was shared with at
  Google, being a user of this installation, gets the same right in Ponistra: an owner and an
  organiser own, an editor and a file organiser edit, a commenter and a reader read. A right is given
  on a folder or file only where it goes beyond what the folder above gives. People outside the
  installation, groups and links are not carried over.
- Only changes: the first pass reads everything. Each later one, every 5 minutes, takes only
  what Google reports as changed: new and changed files are taken again, renamed and moved ones only
  moved, deleted and trashed ones removed. A document imported again keeps its place and versions.
- Read only: while Google stays the original, the folders taken only read in Ponistra, for
  everyone. {t:drive.finishWarning}
- A shared drive is taken once for the whole installation: the first member to take it follows
  it, and the other members reach it through their rights. If that member stops, the next member who
  sees the drive takes it over.
- Stopping: {t:drive.stopWarning}
- What stays out: {t:drive.left} lists what could not be taken, with why:
  {t:drive.why.shortcut}, {t:drive.why.google_only} (forms, sites, maps),
  {t:drive.why.no_download} or {t:drive.why.too_large}. {t:drive.kept} lists the Office files the
  import could not read, which were taken as files.

## Limits

- Mail, calendar and contacts are not taken here but through the connected mail account.
- Without an account connected through Google it shows {t:drive.none} If the administrator has not
  set up signing in through Google, taking cannot begin.
- If Google reports that the account did not allow reading Drive, or that its sign-in ended, taking
  stops: press {t:mail.oauthAgain.google}, then on returning {t:drive.retry}.
- If the Drive API is not enabled in the installation's Google project, the administrator must
  enable it.
- Comments and version history from Google are not carried over.

## Related

- [Mail accounts](help:mail/accounts)
- [Folders and files](help:files/overview)
