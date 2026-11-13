# Links

Links are your saved web addresses, arranged in groups as tiles with an icon, a name and a description.

## How to use it

### A new link

1. In the Documents side column open [links](/links) and press {t:create.new}, then {t:create.link}.
2. Type the {t:tree.address} and, if you like, the {t:tree.name}.
3. Press {t:tree.create}.

### Groups

- {t:create.new} then {t:links.newGroup} makes a group.
- The menu in a group's heading offers {t:create.link} in that group, {t:tree.rename}, {t:links.columns} and {t:tree.toTrash}.
- Under {t:links.columns} you choose how many columns the group lays its tiles in, from one to six, or {t:links.columnsAuto}.
- You move groups and tiles by dragging them; {t:links.moveTo} also moves a link to another group, where {t:links.ungrouped} takes the link out of any group.

### Editing a link

1. A right click on a tile opens a menu with favourites, {t:tree.editLink}, {t:links.moveTo} and {t:tree.toTrash}.
2. In {t:tree.editLink} you change the address and name, and under {t:links.icon} you type the {t:links.iconName}, pick {t:links.removeIcon} or {t:links.pickIcon}
3. Press {t:tree.save}.

An image dropped on a tile becomes that link's icon. For several links at once, long-press one and add the others with a tap or click.

### Loading links

1. Press {t:create.new} then {t:links.load} You can also drop the files on the page.
2. Choose bookmarks exported from a browser (HTML) or a Homepage dashboard (YAML), with images of the icons alongside if you like.

## How it works

A tile opens in a new tab. Ponistra adds `https://` to an address given without it. Once a link is saved it reads the page and takes its title, description and icon, except what you typed yourself; where the page is behind a sign-in, it takes only the site's icon.

{t:links.iconName} takes an image's address or an icon's name as Homepage writes it: a name from dashboard-icons, or one with the prefix `sh-` (selfh.st), `mdi-` (Material Design) or `si-` (Simple Icons).

When loading, each group in the file becomes a group of links and joins an existing one of the same name; a link whose address is already in the group is not made again.

Links are items among your documents, so the search finds them. Below your groups stand the links in the company's folders and in folders shared with you; those you may only read cannot be edited or moved.

## Limits

- The address must be a web address (`http` or `https`).
- One load brings at most 10,000 links.
- While there is no link, it says: {t:links.empty}

## Related

- [The search box](help:start/search)
- [Boards](help:boards/overview)
