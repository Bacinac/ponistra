# Files of guests on computers

The containers and virtual machines on Ponistra OS computers you manage open in {t:rail.files} as folders, and their files are worked on where they are, without copying them and without signing in to the guest.

## How to use it

1. On the module bar, press {t:rail.files}.
2. In the left column, open {t:files.computers}; below it are the computers you manage.
3. Open a computer's branch; below it are its guests, containers and virtual machines. The same guests stand on the {t:rail.files} page while no folder is open, named by computer and guest.
4. Press a guest. It opens at the top of its file system, and a folder opens by pressing its row.

Opening, editing, new folders, uploading, downloading, renaming, moving, deleting and copying work as on a [network location](help:files/network). An item's properties also offer its owner and permissions (Unix).

## How it works

Ponistra does not open a connection to the guest but asks the computer to open it: the computer is always connected to Ponistra and sends the guest's files over that link. So the guest needs neither SSH nor a public address, and the computer may be behind NAT.

The guest opens as its administrator (root), so everything in it can be seen and changed. That is why Ponistra offers it only to those who manage the computer in Computers. A guest with an owner, such as one person's workspace, opens for that owner alone; the computer does not open it even for its manager.

A container opens even when it is not running. A virtual machine opens only while it runs, through the Incus agent inside it.

The computer records every opening as a task with your account. The connection is kept for 2 minutes after the last request, so the next folder does not wait for a new one.

A computer's list of guests is read when you open {t:rail.files} and again after a minute. Guests still being made, or whose making failed, are not shown. A computer that is not connected shows an error below its branch, and the others keep working.

Deleting in a guest is permanent: Ponistra's trash does not keep it. The first change may ask you to [confirm it is you](help:account/confirm).

## Limits

- Only someone who manages at least one computer sees {t:files.computers}.
- A Windows virtual machine has no Incus agent, so its files do not open.
- {t:error.guest_offline} The computer is off or has no network; try again once it is connected.
- {t:error.guest_not_running} Start it in Computers or wait until its agent is up.
- {t:error.guest_owned} Only the guest's owner opens them.
- {t:error.guest_missing} The guest was deleted or renamed meanwhile; refresh the list.
- {t:error.guest_unavailable} Incus is not running on the computer; its state shows in Computers.
- {t:error.guest_refused} The computer refused for another reason, which it records in its tasks.
- {t:error.location_unreachable} and {t:error.location_closed} mean the link to the computer broke; try again.

## Related

- [Files on the network](help:files/network)
- [Files](help:files/manager)
