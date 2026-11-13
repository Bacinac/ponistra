# Contacts

The address book holds the people you correspond with: email addresses, phone numbers, postal addresses and birthdays, in one place for all your accounts and devices.

## How to use it

### Finding and opening

1. Open [contacts](/contacts) on the rail on the left.
2. In the {t:contacts.search} field type the start of a name, company, job title, address or number.
3. Click a contact. On a wide screen it opens beside the list, and while nothing is chosen it says {t:contacts.choose}

### A contact

- An email address opens a new message to the contact, a phone number calls it from a device that can, and a web address opens in a new tab.
- The star {t:contacts.star} or {t:contacts.unstar} beside the name adds the contact to your favourites or removes it; favourites carry the mark {t:contacts.starred}.
- {t:contacts.edit} opens the contact for editing, as [editing a contact](help:contacts/editing) describes.
- The menu beside {t:contacts.edit} holds {t:contacts.addPhoto} ({t:contacts.changePhoto} when there is a photo), {t:contacts.removePhoto} and {t:contacts.delete}, which asks for confirmation ({t:contacts.deleteTitle})

### Several contacts at once

1. Long-press a contact in the list; after that a tap or click adds a contact to the choice or removes it. The choice bar shows {t:explorer.selected} with the number chosen. A right click on a contact offers the same, and {k:Delete} deletes those chosen after you confirm.
2. On the choice bar {t:contacts.write} opens one message to all the chosen who have an email address.
3. {t:contacts.star} and {t:contacts.unstar} change the favourites for all the chosen.
4. {t:contacts.deleteMany} asks for confirmation ({t:contacts.deleteManyTitle}) and deletes the chosen.

Below the list, under {t:mail.mailboxes}, you open the contacts of a [shared mailbox](help:mail/mailboxes) shared with you, and {t:contacts.mailboxOwn} brings back your own.

## How it works

Contacts come by themselves from your connected mail accounts (Google, Microsoft, ActiveSync) and from the organisation's directory, and you can add them yourself. Ponistra takes each person from an account once and joins them with the contact that already has the same address, the same number or the same name; after that the contact is yours and you change it here. Under {t:contacts.sources} the contact says where it came from and when, and below that {t:contacts.changed} with the date of the last change.

A number is found even when you type it without the country code, so 091 finds +385 91 234 5678. A contact without a name is called {t:contacts.unnamed} in the list. When nothing matches the search, it says: {t:contacts.noMatch}

The address book is the same on the web, in the app and on a phone that reads it over CardDAV; {t:contacts.phones} in the page's menu opens the passwords for apps on a phone, as [The Android app](help:phone/android) describes. If an account cannot be reached, the account and the reason show above the list.

## Limits

- A deleted contact disappears from the address book and from the phone, and the account it came from no longer brings it.
- Taking from an account goes one way: a change in Ponistra does not go back to the account the contact came from.

## Related

- [Editing a contact](help:contacts/editing)
- [The organisation's directory](help:contacts/directory)
- [Writing a message](help:mail/composing)
- [Shared mailboxes](help:mail/mailboxes)
