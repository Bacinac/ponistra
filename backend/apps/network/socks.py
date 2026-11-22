"""A connection to a host behind one of the installation's tunnels, through the SOCKS5 port of the
service `tunnel`, the tunnel's id as the user name and the host named to the far side, which
resolves it there. Run as a script it is OpenSSH's ProxyCommand: it hands the connection it made
back to ssh (ProxyUseFdpass) and ends, so no process stays copying the stream. It imports only the
standard library, as ssh starts it with `python -I`."""

import socket
import struct
import sys

SOCKS = ("tunnel", 1080)


class Unreached(OSError):
    """The tunnel is up, but what stands behind it did not answer."""


def opened(
    tunnel: int, host: str, port: int, timeout: float = 20, via: tuple[str, int] | None = None
) -> socket.socket:
    """A connection to host:port behind the tunnel; OSError where it cannot be made."""
    connection = socket.create_connection(via or SOCKS, timeout=timeout)
    try:
        user = str(tunnel).encode()
        connection.sendall(b"\x05\x01\x02")
        if _read(connection, 2) != b"\x05\x02":
            raise OSError("the tunnel service wants no user name")
        connection.sendall(b"\x01" + bytes([len(user)]) + user + b"\x01-")
        if _read(connection, 2) != b"\x01\x00":
            raise OSError(f"the tunnel service holds no tunnel {tunnel}")
        name = host.encode("idna")
        connection.sendall(
            b"\x05\x01\x00\x03" + bytes([len(name)]) + name + struct.pack("!H", port)
        )
        answer = _read(connection, 4)
        if answer[1] != 0:
            raise Unreached(f"the tunnel could not reach {host}:{port} (SOCKS5 {answer[1]})")
        _read(connection, {1: 4, 4: 16}.get(answer[3], 0) + 2)
        connection.settimeout(None)
        return connection
    except BaseException:
        connection.close()
        raise


def _read(connection: socket.socket, size: int) -> bytes:
    read = b""
    while len(read) < size:
        more = connection.recv(size - len(read))
        if not more:
            raise OSError("the tunnel service closed the connection")
        read += more
    return read


def proxy_command(tunnel: int) -> str:
    """The ProxyCommand that reaches ssh's host through the tunnel."""
    host, port = SOCKS
    return f"{sys.executable} -I {__file__} {host} {port} {tunnel} %h %p"


def main(arguments: list[str]) -> int:
    socks_host, socks_port, tunnel, host, port = arguments
    try:
        connection = opened(int(tunnel), host, int(port), via=(socks_host, int(socks_port)))
    except Unreached as failed:
        print(f"tunnel: {failed}", file=sys.stderr)
        return 1
    except OSError as failed:
        print(f"tunnel down: {failed}", file=sys.stderr)
        return 1
    with socket.socket(fileno=sys.stdout.fileno()) as back:
        socket.send_fds(back, [b"\0"], [connection.fileno()])
        back.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
