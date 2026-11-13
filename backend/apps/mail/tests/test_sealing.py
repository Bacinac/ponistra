import base64
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from apps.blobs.tests.uploads import uploaded
from apps.documents.tests.test_views import PNG
from apps.mail import mime, sealing, sync
from apps.mail.imap import imap
from apps.mail.models import Key, Message
from apps.users.models import User

from .mox import LOGIN, SERVER, kept_in_sent, letter, server, synced

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.xdist_group("mox")]


def certified(address: str):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, address)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName([x509.RFC822Name(address)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


@pytest.fixture
def reader(client, account):
    client.force_login(account.owner)
    with imap(*SERVER, LOGIN) as connection:
        sync.sources(connection, account)
    return client


def received(account, folder, raw: bytes) -> Message:
    with server() as client:
        client.append(folder, raw)
    synced(account, folder)
    return Message.objects.get(subject=mime.header(mime.parsed(raw), "Subject"))


def body_entity() -> bytes:
    inner = letter("x")
    inner.set_content("Cijena je 100 €.", cte="quoted-printable")
    inner.add_alternative('<p>Cijena <img src="cid:logo@example.com"></p>', subtype="html")
    inner.get_payload()[1].add_related(PNG, "image", "png", cid="<logo@example.com>")
    inner.add_attachment(b"%PDF-1.7", maintype="application", subtype="pdf", filename="a.pdf")
    return sealing.entity(inner)


def headed(subject: str):
    message = letter(subject)
    message.clear_content()
    return message


def test_a_signed_message_gives_the_bytes_it_signed_and_offers_no_signature(
    reader, account, folder
):
    key, certificate = certified("ana@example.com")
    entity = body_entity()
    signature = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(entity)
        .add_signer(certificate, key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
    )
    message = headed(f"Potpisano {secrets.token_hex(4)}")
    sealing.seal_into(message, sealing.Seal("smime", "signed", signature, entity, "sha-256"))
    kept = received(account, folder, message.as_bytes())
    assert (kept.sealed, kept.attachments) == ("signed", True)
    shown = reader.get(f"/api/mail/messages/{kept.pk}").json()
    assert (shown["sealed"], [each["name"] for each in shown["attachments"]]) == (
        "signed",
        ["a.pdf"],
    )
    assert "Cijena" in shown["html"]
    layer = reader.get(f"/api/mail/messages/{kept.pk}/sealed").json()
    assert (layer["kind"], layer["how"], layer["data"]) == ("smime", "signed", None)
    assert base64.b64decode(layer["content"]) == entity
    assert base64.b64decode(layer["signature"]) == signature


def test_an_encrypted_message_is_opened_in_the_browser_and_read_without_anything_from_outside(
    reader, account, folder
):
    key, certificate = certified("mox@localhost")
    entity = body_entity().replace(b"<p>Cijena", b'<p><img src="https://spy.example/x.png">Cijena')
    data = (
        pkcs7.PKCS7EnvelopeBuilder()
        .set_data(entity)
        .add_recipient(certificate)
        .encrypt(serialization.Encoding.DER, [])
    )
    message = headed(f"Tajno {secrets.token_hex(4)}")
    sealing.seal_into(message, sealing.Seal("smime", "encrypted", data))
    kept = received(account, folder, message.as_bytes())
    assert (kept.sealed, kept.attachments, kept.files.count()) == ("encrypted", False, 0)
    shown = reader.get(f"/api/mail/messages/{kept.pk}").json()
    assert (shown["html"], shown["text"], shown["attachments"]) == (None, "", [])
    layer = reader.get(f"/api/mail/messages/{kept.pk}/sealed").json()
    assert (layer["kind"], layer["how"]) == ("smime", "encrypted")
    opened = pkcs7.pkcs7_decrypt_der(base64.b64decode(layer["data"]), certificate, key, [])
    assert opened == entity
    read = reader.post(
        f"/api/mail/messages/{kept.pk}/unsealed", opened, content_type="application/octet-stream"
    ).json()
    assert read["remote"] is True and "spy.example" not in read["html"]
    assert f'src="data:image/png;base64,{base64.b64encode(PNG).decode()}"' in read["html"]
    assert [(each["name"], base64.b64decode(each["data"])) for each in read["files"]] == [
        ("a.pdf", b"%PDF-1.7")
    ]


def test_what_opens_into_another_seal_is_given_back_as_that_seal(reader, account, folder):
    kept = received(account, folder, letter(f"Omot {secrets.token_hex(4)}").as_bytes())
    inner = headed("x")
    sealing.seal_into(
        inner,
        sealing.Seal(
            "pgp", "encrypted", b"-----BEGIN PGP MESSAGE-----\n\nx\n-----END PGP MESSAGE-----\n"
        ),
    )
    read = reader.post(
        f"/api/mail/messages/{kept.pk}/unsealed",
        inner.as_bytes(),
        content_type="application/octet-stream",
    ).json()
    assert read["layer"]["kind"] == "pgp" and read["layer"]["how"] == "encrypted"
    assert base64.b64decode(read["layer"]["data"]).startswith(b"-----BEGIN PGP MESSAGE-----")
    assert reader.get(f"/api/mail/messages/{kept.pk}/sealed").status_code == 404


def test_a_pgp_block_in_the_text_is_a_seal_of_its_own():
    message = letter("x", "Evo:\n-----BEGIN PGP MESSAGE-----\n\nwcBMA\n-----END PGP MESSAGE-----\n")
    found = sealing.layer(message.as_bytes())
    assert (found.kind, found.how, found.inline) == ("pgp", "encrypted", True)
    assert found.data.endswith(b"-----END PGP MESSAGE-----")


def test_a_message_signed_with_pgp_travels_with_the_bytes_signed_untouched():
    entity = body_entity()
    signature = b"-----BEGIN PGP SIGNATURE-----\n\nwsBc\n-----END PGP SIGNATURE-----\n"
    message = headed("x")
    sealing.seal_into(message, sealing.Seal("pgp", "signed", signature, entity, "pgp-sha256"))
    raw = message.as_bytes()
    assert b'micalg="pgp-sha256"' in raw and b'protocol="application/pgp-signature"' in raw
    found = sealing.layer(raw)
    assert (found.kind, found.content) == ("pgp", entity)
    assert found.signature == signature.replace(b"\n", b"\r\n").rstrip(b"\r\n")


def test_a_sealed_message_leaves_with_what_the_browser_sealed_and_shares_nothing(reader, account):
    subject = f"Zapecaceno {secrets.token_hex(4)}"
    given = {
        "account": account.pk,
        "to": [{"address": "ana@example.com"}],
        "subject": subject,
        "html": "<p>Cijena je 100 €.</p>",
    }
    entity = base64.b64decode(
        reader.post("/api/mail/sealing", given, content_type="application/json").json()["entity"]
    )
    assert b"Cijena je 100" in entity and b"Subject" not in entity
    key, certificate = certified("mox@localhost")
    signature = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(entity)
        .add_signer(certificate, key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
    )
    sealed = {
        "kind": "smime",
        "how": "signed",
        "micalg": "sha-256",
        "entity": uploaded(reader, entity)["sha256"],
        "data": uploaded(reader, signature)["sha256"],
    }
    shared = {"shared": [{"node": "00000000-0000-0000-0000-000000000000", "role": "read"}]}
    refused = reader.post("/api/mail/sealing", given | shared, content_type="application/json")
    assert refused.json() == {"error": "sealed_shared"}
    answer = reader.post(
        "/api/mail/send", given | {"sealed": sealed}, content_type="application/json"
    )
    assert answer.json() == {"refused": [], "kept": True}
    mine = Message.objects.get(folder__role="sent", subject=subject)
    assert mine.sealed == "signed"
    found = kept_in_sent(subject)
    assert found.get_content_type() == "multipart/signed"
    assert (
        sealing.layer(found.as_bytes(policy=found.policy.clone(linesep="\r\n"))).content == entity
    )


def test_own_keys_reach_colleagues_and_met_keys_only_their_owner(reader, account):
    colleague = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    _, certificate = certified("mox@localhost")
    der = certificate.public_bytes(serialization.Encoding.DER)
    fingerprint = certificate.fingerprint(hashes.SHA256()).hex()
    for own, address in ((True, "ivo@example.com"), (False, "iva@example.com")):
        made = reader.post(
            "/api/mail/keys",
            {
                "kind": "smime",
                "address": address.upper(),
                "fingerprint": fingerprint,
                "data": base64.b64encode(der).decode(),
                "own": own,
                "expires_at": certificate.not_valid_after_utc.isoformat(),
            },
            content_type="application/json",
        )
        assert made.status_code == 201
    assert Key.objects.filter(owner=account.owner).count() == 2
    reader.force_login(colleague)
    asked = "/api/mail/keys?address=ivo@example.com&address=iva@example.com"
    [seen] = reader.get(asked).json()["keys"]
    assert (seen["address"], seen["own"], seen["mine"]) == ("ivo@example.com", True, False)
    assert reader.delete(f"/api/mail/keys/{seen['id']}").status_code == 404


def test_a_message_signed_and_encrypted_with_smime_is_signed_inside(reader, account):
    given = {"account": account.pk, "to": [{"address": "ana@example.com"}], "html": "<p>Tajna</p>"}
    entity = base64.b64decode(
        reader.post("/api/mail/sealing", given, content_type="application/json").json()["entity"]
    )
    key, certificate = certified("ivo@example.com")
    signature = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(entity)
        .add_signer(certificate, key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
    )
    signed = {
        "kind": "smime",
        "how": "signed",
        "micalg": "sha-256",
        "entity": uploaded(reader, entity)["sha256"],
        "data": uploaded(reader, signature)["sha256"],
    }
    made = reader.post("/api/mail/sealing/signed", signed, content_type="application/json")
    inner = base64.b64decode(made.json()["entity"])
    found = sealing.layer(inner)
    assert (found.kind, found.how, found.content, found.signature) == (
        "smime",
        "signed",
        entity,
        signature,
    )
    refused = reader.post(
        "/api/mail/sealing/signed", signed | {"kind": "pgp"}, content_type="application/json"
    )
    assert refused.json() == {"error": "invalid_sealed"}
