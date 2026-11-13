import base64
import socket
import ssl
import threading

import pytest

from apps.mail import imap


def test_a_sending_server_that_hangs_up_on_the_password_refused_it(settings):
    listener = socket.create_server(("127.0.0.1", 0))

    def serve():
        connection, _ = listener.accept()
        with connection, connection.makefile("rwb") as stream:
            stream.write(b"220 ready\r\n")
            stream.flush()
            stream.readline()
            stream.write(b"250-hello\r\n250 AUTH PLAIN LOGIN\r\n")
            stream.flush()
            stream.readline()

    threading.Thread(target=serve, daemon=True).start()
    settings.MAIL_PLAIN_HOSTS = {"127.0.0.1"}
    with listener, pytest.raises(imap.Failed) as refused:
        given = imap.Login("ana", password="wrong")
        imap.smtp_checked("127.0.0.1", listener.getsockname()[1], "none", given)
    assert refused.value.code == "smtp_login"


def test_a_sending_server_that_refuses_the_token_is_answered_and_says_so(settings, caplog):
    listener = socket.create_server(("127.0.0.1", 0))
    heard = []

    def serve():
        connection, _ = listener.accept()
        with connection, connection.makefile("rwb") as stream:
            stream.write(b"220 ready\r\n")
            stream.flush()
            stream.readline()
            stream.write(b"250-hello\r\n250 AUTH XOAUTH2\r\n")
            stream.flush()
            heard.append(stream.readline())
            stream.write(b"334 " + base64.b64encode(b'{"status":"401"}') + b"\r\n")
            stream.flush()
            heard.append(stream.readline())
            stream.write(b"535 5.7.8 refused\r\n")
            stream.flush()
            stream.readline()

    threading.Thread(target=serve, daemon=True).start()
    settings.MAIL_PLAIN_HOSTS = {"127.0.0.1"}
    with listener, pytest.raises(imap.Failed) as refused:
        given = imap.Login("ana@example.com", token="expired")
        imap.smtp_checked("127.0.0.1", listener.getsockname()[1], "none", given)
    assert refused.value.code == "smtp_oauth_login"
    command, mechanism, payload = heard[0].split()
    assert (command, mechanism) == (b"AUTH", b"XOAUTH2")
    assert base64.b64decode(payload) == b"user=ana@example.com\1auth=Bearer expired\1\1"
    assert heard[1] == b"\r\n"
    assert "535" in caplog.text and "5.7.8 refused" in caplog.text
    assert "expired" not in caplog.text


def _certified(tmp_path):
    from datetime import UTC, datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mail.test")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("mail.test")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert = tmp_path / "cert.pem"
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private = tmp_path / "key.pem"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert, private


def _resolving(monkeypatch, *listeners):
    addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", it.getsockname()) for it in listeners]
    monkeypatch.setattr(imap.socket, "getaddrinfo", lambda *args, **kwargs: addresses)
    monkeypatch.setattr(imap, "HANDSHAKE", 0.5)


def test_a_server_address_stalling_in_the_handshake_gives_way_to_the_next(tmp_path, monkeypatch):
    cert, key = _certified(tmp_path)
    stalling = socket.create_server(("127.0.0.1", 0))
    answering = socket.create_server(("127.0.0.1", 0))
    serving = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    serving.load_cert_chain(cert, key)

    def serve():
        connection, _ = answering.accept()
        with serving.wrap_socket(connection, server_side=True) as reached:
            reached.sendall(b"* OK ready\r\n")
            reached.recv(1)

    threading.Thread(target=serve, daemon=True).start()
    _resolving(monkeypatch, stalling, answering)
    trusting = ssl.create_default_context(cafile=str(cert))
    with stalling, answering, imap.encrypted("mail.test", 993, trusting) as reached:
        assert reached.recv(10) == b"* OK ready"
        assert reached.gettimeout() == imap.TIMEOUT


def test_a_server_whose_every_address_stalls_cannot_be_reached(monkeypatch):
    stalling = socket.create_server(("127.0.0.1", 0))
    _resolving(monkeypatch, stalling, stalling)
    with stalling, pytest.raises(imap.Failed) as lost:
        imap.connected("mail.test", 993, "tls", imap.Login("ana", password="secret"))
    assert lost.value.code == "imap_unreachable"
