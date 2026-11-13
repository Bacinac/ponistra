# Off-site copy

The installation's backups are mirrored, encrypted, into an S3 bucket away from the server that refuses deleting, and the recovery kit brings the installation back on a new server from them.

## How to use it

### Setting up the bucket

1. On the {t:health.title} page, under {t:health.offsite}, press {t:health.offsite.set} or, once the copy is set up, {t:health.offsite.change}
2. With a provider, for example Cloudflare R2, open a bucket and an access key as the dialog's instructions describe.
3. Enter the {t:health.offsite.endpoint}, {t:health.offsite.bucket}, {t:health.offsite.accessKey} and {t:health.offsite.secret}.
4. Press {t:health.offsite.save}. While it runs, the button shows: {t:health.offsite.checking}
5. In the {t:health.kit.title} dialog, press {t:health.kit.copy} or {t:health.kit.download} and keep the kit away from the server.

### A new recovery kit

1. Press {t:health.kit.renew}
2. Confirm with {t:health.kit.renewConfirm} and keep the new kit as when setting up.

## How it works

Before saving, Ponistra checks that the bucket answers to the keys entered. The secret is stored locked; afterwards only {t:health.offsite.secretKept} and its last four characters are shown. An empty field keeps the stored secret only while the endpoint, bucket and access key stay the same. When the stored secret can no longer be read, the page says: {t:health.offsite.secretLost}

Each new backup, and the database's changes and the files saved every 15 minutes between them, is mirrored file by file within 10 minutes of being made; the bucket is only added to. If the server is lost, `ponistra recover` brings the installation back to the last moment mirrored so. Ponistra tries to delete a test file in the bucket, so under {t:health.offsite.protection} it says {t:health.offsite.protected} or {t:health.offsite.unprotected}. Every 28 days a new full copy with every file begins, and beside {t:health.offsite.generation} the page shows when; older ones go as their locks run out. Until the newest backup is mirrored, the page says: {t:health.offsite.late}

Once a day, after mirroring, the copy in the bucket is checked, a different part of the data each night, so every part is read within 28 days. Every 30 days, or after a failed attempt, Ponistra restores the newest copy from the bucket, with every change to the database saved after it, on trial into a separate database, checks that the bucket holds every file that database names, and then removes it. Beside {t:health.offsite.mirrored}, {t:health.offsite.checked} and {t:health.offsite.tried} the page shows when each last happened, and below how many documents, folders and files the trial restore brought back.

### Recovery kit

The kit holds the endpoint, the bucket, the access key, the secret and an emergency key. The emergency key is shown only in that dialog and kept nowhere else. Every save of the bucket and every new kit make a new emergency key and remove the previous one from the server. With the kit, the `ponistra recover` command brings the installation back on a new server.

## Limits

- Whoever holds the recovery kit can read every backup.
- While a backup is being made, the bucket cannot be changed and no kit can be made.
- To save the bucket or make a new kit, Ponistra may ask you to confirm it is you.

## Related

- [System health](help:admin/health)
- [Confirming it is you](help:account/confirm)
