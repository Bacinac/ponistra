import socket
import subprocess
import sys

import pytest

from apps.network import socks


def test_a_host_behind_a_tunnel_is_reached_through_the_service(far, answering):
    with socks.opened(7, "127.0.0.1", answering) as connection:
        assert connection.recv(8) == b"far side"
    assert far == [("127.0.0.1", answering)]
    with pytest.raises(OSError, match="holds no tunnel 8"):
        socks.opened(8, "127.0.0.1", answering)


def test_what_does_not_answer_behind_the_tunnel_is_told_apart(far):
    closed = socket.create_server(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    with pytest.raises(socks.Unreached):
        socks.opened(7, "127.0.0.1", port)


def _proxied(*arguments: str) -> tuple[subprocess.CompletedProcess, socket.socket | None]:
    ours, theirs = socket.socketpair()
    with ours, theirs:
        done = subprocess.run(
            [sys.executable, "-I", socks.__file__, *arguments],
            stdout=theirs,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        theirs.close()
        if done.returncode:
            return done, None
        _, [handed], _, _ = socket.recv_fds(ours, 1, 1)
        return done, socket.socket(fileno=handed)


def test_as_ssh_s_proxy_command_it_hands_back_the_connection_and_ends(far, answering):
    host, port = socks.SOCKS
    done, handed = _proxied(host, str(port), "7", "127.0.0.1", str(answering))
    assert done.returncode == 0, done.stderr
    with handed:
        assert handed.recv(8) == b"far side"
    assert socks.proxy_command(7).endswith(f" -I {socks.__file__} {host} {port} 7 %h %p")


def test_as_ssh_s_proxy_command_it_says_why_the_tunnel_did_not_carry(far, answering):
    host, port = socks.SOCKS
    done, _ = _proxied(host, str(port), "8", "127.0.0.1", str(answering))
    assert done.returncode == 1
    assert done.stderr.decode().startswith("tunnel down: the tunnel service holds no tunnel 8")
