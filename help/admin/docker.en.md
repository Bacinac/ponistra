# Docker hosts

Docker on a server the installation reaches over SSH: stacks from folders with a compose file are run in Files, and the host's containers, images, volumes and networks on its own page.

## How to use it

### New host

1. In [Files](/files) add the server as an [SFTP location](help:documents/locations), if it is not one yet.
2. Open {t:admin.title}, choose {t:network.title} and under {t:docker.hosts} press {t:docker.hostNew}.
3. Choose the location and press {t:docker.hostAdd}.
4. In the host's row press {t:docker.copyAuthorized} and add the copied line to `~/.ssh/authorized_keys` of that location's account on the server. The account must be in the `docker` group.
5. In the row's menu choose {t:docker.hostOpen}; once the page shows the Docker version, the host works.

The message {t:docker.noCandidates} means you own no SFTP location that is not a host already.

### A stack in Files

1. In [Files](/files) open the host's location under {t:locations.title} and go into the stack's folder, a folder with a `compose.yaml`, `compose.yml`, `docker-compose.yaml` or `docker-compose.yml` file.
2. Above the files stands {t:docker.stack} with its containers and their state, or {t:docker.stackDown} while the stack is not running.
3. Press {t:docker.verb.up} to start the stack, or in the menu beside it choose {t:docker.verb.pull}, {t:docker.verb.restart}, {t:docker.verb.stop} or {t:docker.verb.down}. A window writes out what Docker Compose does and how it ended.
4. You edit the compose file like any other text file: open it with a double click, and apply the change with {t:docker.verb.up}.
5. At the root of the location the {t:docker.host} button leads to the host's page.

### A container

In the menu of a container's row, in the stack or on the host's page:

- {t:docker.logs} opens the last 500 lines of its log and adds new ones while the window is open.
- {t:docker.shell} opens a terminal in a running container.
- {t:docker.start}, {t:docker.stop} and {t:docker.restart} change its state.

### The host's page

1. Open it from the host's row in {t:network.title} or with the {t:docker.host} button in Files.
2. The tabs {t:docker.kind.containers}, {t:docker.kind.images}, {t:docker.kind.volumes} and {t:docker.kind.networks} list everything Docker on the host holds, marking {t:docker.unused} what no container holds.
3. You remove a single unused item from its row's menu with {t:docker.remove}; a stopped container too.
4. The buttons above the list remove everything unused at once: {t:docker.prune.containers}, {t:docker.prune.images}, {t:docker.prune.builder}, {t:docker.prune.volumes} and {t:docker.prune.networks}. After you confirm, a line below says how much was removed and how much space was freed.

### Removing a host

1. In {t:network.title}, in the host row's menu, choose {t:docker.hostRemove} and confirm.
2. On the server delete the line from `authorized_keys`.

## How it works

The installation makes a key of its own, ed25519, for each host and keeps it sealed with the installation's secret key; the location's key for files stays separate. The line for `authorized_keys` carries a forced command: with that key the server runs only `docker system dial-stdio`, through which the installation talks to Docker's API, and `docker compose` with one of the five stack actions in the given folder. To any other command the page answers {t:error.docker_command_refused} with what the server said. Docker on a host is worth as much as root on it, so only administrators see and change it.

The connection takes the same way as the location's files: the same server, the server key the location remembered, the jump host and the [VPN tunnel](help:admin/tunnels) if the location uses one. The location's owner adds the host; an administrator the location is shared with for editing manages it, and one who may only read it sees its state and logs.

{t:docker.verb.up} runs `docker compose up -d --remove-orphans`, so the containers the compose file dropped are removed. Every change on a host asks for a [fresh confirmation](help:account/confirm) if the last one is not recent.

The installation follows Docker's events on every host, so the stack, the lists and the states on open pages refresh by themselves when a container starts or stops, also when someone does it outside Ponistra. When a host cannot be reached, it tries again, first after five seconds, then ever more rarely, up to five minutes.

Removing a host deletes only its key in the installation; the location, its files and everything on the server stay.

## Limits

- Only an SFTP location can be a Docker host ({t:error.docker_needs_sftp}), and only once ({t:error.docker_host_exists}).
- The forced command does not allow `build` nor the other commands of Docker Compose; images are built elsewhere and pulled with {t:docker.verb.pull}.
- The shell works only in a running container; it uses `bash` if the container has it, else `sh`.
- {t:docker.prune.volumes} deletes named volumes no container uses too, with their data; a stack taken down with {t:docker.verb.down} is left without them.
- {t:error.docker_denied} means the account is not in the group: add the account to the `docker` group on the server and sign in with it again.
- {t:error.docker_missing} and {t:error.docker_compose_missing} mean Docker Engine with its Compose plugin has to be installed on the server.
- {t:error.docker_down} means Docker's service is not running on the server; below every message stands what Docker itself said.
- {t:error.docker_stack_missing} means the folder was removed or renamed meanwhile.
- {t:error.docker_conflict} means a container still uses the item; stop or remove it first.
- {t:error.docker_secret_lost} means the installation's secret key was changed; remove the host, add it again and replace the line in `authorized_keys`.

## Related

- [Locations](help:documents/locations)
- [Network in Files](help:files/network)
- [VPN tunnels](help:admin/tunnels)
- [Network](help:admin/network)
