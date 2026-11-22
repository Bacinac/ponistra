import socket
import threading

import pytest

from apps.network import socks

HELD = 7


def _pumped(source: socket.socket, sink: socket.socket) -> None:
    try:
        while data := source.recv(65536):
            sink.sendall(data)
    except OSError:
        pass
    finally:
        for each in (source, sink):
            try:
                each.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _relayed(connection: socket.socket, asked: list) -> None:
    connection.recv(3)
    connection.sendall(b"\x05\x02")
    head = connection.recv(2)
    user = connection.recv(head[1]).decode()
    connection.recv(connection.recv(1)[0])
    if user != str(HELD):
        connection.sendall(b"\x01\x01")
        connection.close()
        return
    connection.sendall(b"\x01\x00")
    request = connection.recv(5)
    name = connection.recv(request[4]).decode()
    port = int.from_bytes(connection.recv(2))
    asked.append((name, port))
    try:
        far = socket.create_connection((name, port), timeout=10)
    except OSError:
        connection.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
        connection.close()
        return
    far.settimeout(None)
    connection.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
    threading.Thread(target=_pumped, args=(connection, far), daemon=True).start()
    threading.Thread(target=_pumped, args=(far, connection), daemon=True).start()


@pytest.fixture
def far(monkeypatch):
    """The tunnel service's SOCKS5 port, holding the tunnel 7 and connecting to what is asked
    behind it; the hosts asked, as the far side was named them."""
    listener = socket.create_server(("127.0.0.1", 0))
    asked: list = []

    def serve():
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            threading.Thread(target=_relayed, args=(connection, asked), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    monkeypatch.setattr(socks, "SOCKS", listener.getsockname())
    yield asked
    listener.close()


@pytest.fixture
def answering():
    """A server behind the tunnel that says `far side` to whoever connects."""
    listener = socket.create_server(("127.0.0.1", 0))

    def serve():
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            with connection:
                connection.sendall(b"far side")

    threading.Thread(target=serve, daemon=True).start()
    yield listener.getsockname()[1]
    listener.close()
