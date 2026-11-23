"""Which Docker hosts an administrator reaches, and the line for the server's `authorized_keys`."""

from dataclasses import replace

from apps.access.models import Role
from apps.core.api import Refused
from apps.core.asyncdb import database
from apps.core.sealed import opened
from apps.locations import reach as locations
from apps.locations.models import Location
from apps.locations.remote import Failed
from apps.locations.sftp import Target
from apps.network.models import Tunnel

from .engine import Engine
from .models import Host

SEALED = "docker_host"

# The command the host's sshd forces on Ponistra's key, whatever it asked: the Engine API, or
# `docker compose` with one of a few verbs in a stack's folder, its output and errors as one stream.
# The folder follows ` -- ` as it is, so no name in it is read by a shell.
COMMAND = (
    "c=$SSH_ORIGINAL_COMMAND; case $c in "
    "'docker system dial-stdio') exec docker system dial-stdio;; "
    "'docker compose '*' -- '*) ;; "
    "*) echo 'ponistra: refused' >&2; exit 126;; esac; "
    "v=${c#docker compose }; d=${v#* -- }; v=${v%% -- *}; "
    "case $v in up) set -- up -d --remove-orphans;; ps) set -- ps --all --format json;; "
    "pull|start|stop|restart|down) set -- $v;; "
    "*) echo 'ponistra: refused' >&2; exit 126;; esac; "
    'cd -- "$d" && exec docker compose "$@" 2>&1'
)


def authorized(public_key: str) -> str:
    """The line for `~/.ssh/authorized_keys` of the account on the host."""
    command = COMMAND.replace("\\", "\\\\").replace('"', '\\"')
    return f'restrict,command="{command}" {public_key}'


def host(user, pk, needs: Role = Role.READ) -> Host:
    """The Docker host on the location the request names, for an administrator whose role on the
    location covers what the request does."""
    if not user.is_staff:
        raise Refused(403, "forbidden")
    found, _ = locations.location(user, pk, needs)
    held = Host.objects.filter(location=found).first()
    if held is None:
        raise Refused(404, "docker_host_missing")
    held.location = found
    return held


def target(held: Host) -> Target:
    secret = opened(SEALED, held.secret)
    if secret is None:
        raise Failed("docker_secret_lost")
    return replace(locations.target(held.location, secret), password=None, key=secret)


def _known(pk, known_hosts: str) -> None:
    Location.objects.filter(pk=pk).update(known_hosts=known_hosts)


def engine(held: Host) -> Engine:
    """The host's daemon, a location behind a tunnel reached only while the tunnel is up; the
    server's host keys first found are kept with the location, which is the same server."""
    tunnel = held.location.tunnel_id
    if tunnel is not None and not Tunnel.objects.filter(pk=tunnel, state=Tunnel.State.UP).exists():
        raise Failed("location_tunnel_down")
    reached = target(held)

    async def learned(known: str) -> None:
        await database(_known)(held.location_id, known)

    return Engine(reached, learned)


@database
def reached(user, pk, needs: Role = Role.READ) -> tuple[Host, Engine]:
    held = host(user, pk, needs)
    return held, engine(held)
