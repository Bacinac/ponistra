import hashlib
import io
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from functools import partial
from urllib.parse import parse_qs, unquote, urlsplit
from xml.sax.saxutils import escape

import httpx2
import psycopg
import pytest
from django.conf import settings as django_settings
from django.utils import timezone

from apps.backups import backups, bucket, offsite
from apps.backups.models import Offsite
from apps.blobs import store
from apps.blobs.models import Blob
from apps.core import sealed
from apps.journal.models import Entry
from apps.users.models import User

pytestmark = pytest.mark.django_db(transaction=True)

ENDPOINT = "https://account.eu.r2.cloudflarestorage.com"
NAME = "ponistra-backup"
ACCESS = "a" * 32
SECRET = "s" * 64


class FakeBucket:
    """An S3 bucket in memory, as R2 answers: a lock refuses deleting and overwriting what it
    holds, and a listing comes a few objects a page."""

    def __init__(self):
        self.objects: dict[str, tuple[bytes, datetime]] = {}
        self.locked = lambda key: False
        self.puts: list[str] = []
        self.reachable = True

    def answer(self, status: int, code: str = "", content: bytes = b"") -> httpx2.Response:
        if code:
            content = f"<Error><Code>{code}</Code></Error>".encode()
        return httpx2.Response(status, content=content)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if not self.reachable:
            raise httpx2.ConnectError("refused", request=request)
        if f"Credential={ACCESS}/" not in request.headers["authorization"]:
            return self.answer(403, "SignatureDoesNotMatch")
        parts = urlsplit(str(request.url))
        name, _, key = unquote(parts.path).lstrip("/").partition("/")
        if name != NAME:
            return self.answer(404, "NoSuchBucket")
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        if request.method == "GET" and not key:
            return self.listing(query)
        if request.method == "GET":
            found = self.objects.get(key)
            return self.answer(200, content=found[0]) if found else self.answer(404, "NoSuchKey")
        if request.method == "PUT":
            body = request.read()
            if hashlib.sha256(body).hexdigest() != request.headers["x-amz-content-sha256"]:
                return self.answer(400, "XAmzContentSHA256Mismatch")
            if key in self.objects and self.locked(key):
                return self.answer(409, "ObjectLockedByBucketPolicy")
            self.objects[key] = (body, datetime.now(UTC))
            self.puts.append(key)
            return self.answer(200)
        if self.locked(key):
            return self.answer(409, "ObjectLockedByBucketPolicy")
        self.objects.pop(key, None)
        return self.answer(204)

    def listing(self, query: dict) -> httpx2.Response:
        prefix, delimiter = query.get("prefix", ""), query.get("delimiter", "")
        keys, prefixes = [], set()
        for key in sorted(self.objects):
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix) :]
            if delimiter and delimiter in rest:
                prefixes.add(prefix + rest.split(delimiter)[0] + delimiter)
            else:
                keys.append(key)
        start = int(query.get("continuation-token", "0"))
        page = keys[start : start + 3]
        more = start + 3 < len(keys)
        contents = "".join(
            f"<Contents><Key>{escape(key)}</Key><LastModified>"
            f"{self.objects[key][1].isoformat().replace('+00:00', 'Z')}</LastModified></Contents>"
            for key in page
        )
        common = "".join(
            f"<CommonPrefixes><Prefix>{escape(found)}</Prefix></CommonPrefixes>"
            for found in sorted(prefixes)
        )
        token = f"<NextContinuationToken>{start + 3}</NextContinuationToken>" if more else ""
        xml = (
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<IsTruncated>{'true' if more else 'false'}</IsTruncated>{token}{contents}{common}"
            "</ListBucketResult>"
        )
        return self.answer(200, content=xml.encode())


@pytest.fixture
def fake(monkeypatch):
    found = FakeBucket()
    monkeypatch.setattr(
        offsite, "Bucket", partial(bucket.Bucket, transport=httpx2.MockTransport(found))
    )
    return found


@pytest.fixture
def admin(client):
    client.user = User.objects.create_superuser("ivo@example.com", "Kamen-Most-Rijeka-71")
    client.force_login(client.user)
    return client


def setting(**changed) -> dict:
    return {"endpoint": ENDPOINT, "bucket": NAME, "access_key": ACCESS, "secret": SECRET, **changed}


def configured() -> Offsite:
    """The bucket as saved, without the emergency key that only the kit needs."""
    return Offsite.objects.create(
        endpoint=ENDPOINT,
        bucket=NAME,
        access_key=ACCESS,
        secret=sealed.seal("offsite secret", SECRET),
        hint=SECRET[-4:],
        changed_at=timezone.now(),
    )


def emergency_keys() -> list[str]:
    keys = json.loads(backups.restic("key", "list", "--json"))
    return [key["id"] for key in keys if key["userName"] == offsite.EMERGENCY]


def opens(directory, password: str) -> list[str]:
    listed = subprocess.run(
        [
            "restic",
            "-r",
            str(directory),
            "--no-lock",
            "snapshots",
            "--json",
            f"--host={backups.HOST}",
        ],
        env={**os.environ, "RESTIC_PASSWORD": password},
        capture_output=True,
        text=True,
        check=True,
    )
    return [snapshot["short_id"] for snapshot in json.loads(listed.stdout)]


def test_only_an_administrator_sets_the_offsite_copy(api, fake):
    assert api.patch("/api/backups/offsite", setting(), "application/json").status_code == 403
    assert api.post("/api/backups/offsite/kit").status_code == 403


@pytest.mark.parametrize(
    ("changed", "code"),
    [
        ({"endpoint": "http://plain.example"}, "invalid_endpoint"),
        ({"bucket": "Not_A_Bucket"}, "invalid_bucket"),
        ({"access_key": " "}, "invalid_access_key"),
    ],
)
def test_a_malformed_setting_is_refused(admin, fake, changed, code):
    response = admin.patch("/api/backups/offsite", setting(**changed), "application/json")
    assert (response.status_code, response.json()["error"]) == (400, code)


def test_the_bucket_is_checked_before_it_is_kept(admin, fake):
    wrong = admin.patch("/api/backups/offsite", setting(bucket="other"), "application/json")
    assert wrong.json()["error"] == "offsite_no_bucket"
    refused = admin.patch("/api/backups/offsite", setting(access_key="b" * 32), "application/json")
    assert refused.json()["error"] == "offsite_refused"
    fake.reachable = False
    gone = admin.patch("/api/backups/offsite", setting(), "application/json")
    assert gone.json()["error"] == "offsite_unreachable"
    assert not Offsite.objects.exists()


def test_a_saved_bucket_gives_a_kit_whose_emergency_key_opens_the_snapshots(admin, fake, tmp_path):
    response = admin.patch("/api/backups/offsite", setting(), "application/json")
    kit = response.json()["kit"]
    assert {k: kit[k] for k in ("endpoint", "bucket", "access_key", "secret")} == setting()
    snapshot = backups.backup()
    assert opens(tmp_path / "repository", kit["emergency"]) == [snapshot]
    found = Offsite.objects.get()
    assert (found.hint, found.changed_by, offsite.opened(found)) == (
        SECRET[-4:],
        admin.user,
        SECRET,
    )
    assert SECRET.encode() not in bytes(found.secret)


def test_a_new_kit_takes_the_place_of_the_old(admin, fake):
    first = admin.patch("/api/backups/offsite", setting(), "application/json").json()["kit"]
    again = admin.post("/api/backups/offsite/kit").json()["kit"]
    assert again["emergency"] != first["emergency"]
    assert len(emergency_keys()) == 1
    kept = admin.patch("/api/backups/offsite", setting(secret=None), "application/json")
    assert kept.json()["kit"]["secret"] == SECRET
    other = admin.patch(
        "/api/backups/offsite", setting(access_key="b" * 32, secret=None), "application/json"
    )
    assert other.json()["error"] == "offsite_secret_needed"
    assert [(entry.actor, entry.detail) for entry in Entry.objects.order_by("id")] == [
        (admin.user, {"setting": "offsite", "change": "changed"}),
        (admin.user, {"setting": "offsite_kit", "change": "changed"}),
        (admin.user, {"setting": "offsite", "change": "changed"}),
    ]


def test_no_kit_while_a_snapshot_or_mirror_runs(admin, fake):
    configured()
    database = django_settings.DATABASES["default"]
    with psycopg.connect(
        host=database["HOST"],
        port=database["PORT"],
        user=database["USER"],
        password=database["PASSWORD"],
        dbname=database["NAME"],
    ) as other:
        other.execute("SELECT pg_advisory_lock(%s)", [backups.LOCK])
        response = admin.post("/api/backups/offsite/kit")
    assert (response.status_code, response.json()["error"]) == (422, "offsite_busy")


def test_the_mirror_copies_the_repository_but_its_locks_and_fetch_brings_it_back(fake, tmp_path):
    found = configured()
    snapshot = backups.backup()
    offsite.mirrored()
    today = timezone.localdate().isoformat()
    keys = set(fake.objects)
    assert f"{today}.canary" in keys and f"{today}/config" in keys
    assert not any("/locks/" in key for key in keys)
    assert fake.puts.index(f"{today}/config") < min(
        fake.puts.index(key) for key in keys if "/snapshots/" in key
    )
    into = tmp_path / "fetched"
    into.mkdir()
    target = bucket.Bucket(ENDPOINT, NAME, ACCESS, SECRET, transport=httpx2.MockTransport(fake))
    assert bucket.fetch(target, into) == today
    assert opens(into, "test") == [snapshot]
    found.refresh_from_db()
    assert (found.generation, found.protected, found.error) == (today, False, "")


def test_a_second_mirror_adds_only_what_is_new(fake):
    configured()
    backups.backup()
    offsite.mirrored()
    fake.puts.clear()
    backups.backup()
    offsite.mirrored()
    assert any("/snapshots/" in key for key in fake.puts)
    assert not any(key.endswith("/config") or "/keys/" in key for key in fake.puts)


def test_a_new_kit_reaches_the_bucket_before_the_next_snapshot(fake, tmp_path):
    found = configured()
    snapshot = backups.backup()
    offsite.mirrored()
    before = offsite.state(found)
    key = offsite.reissued()
    assert offsite.state(found) != before
    offsite.mirrored()
    into = tmp_path / "fetched"
    into.mkdir()
    target = bucket.Bucket(ENDPOINT, NAME, ACCESS, SECRET, transport=httpx2.MockTransport(fake))
    bucket.fetch(target, into)
    assert opens(into, key) == [snapshot]


def test_a_locked_bucket_is_protected_and_an_unlocked_one_says_so(fake):
    configured()
    offsite.mirrored()
    assert Offsite.objects.get().protected is False
    assert f"{timezone.localdate().isoformat()}.canary" in fake.objects
    fake.locked = lambda key: True
    offsite.mirrored()
    assert Offsite.objects.get().protected is True


def test_a_generation_period_old_gives_way_to_a_new_one_as_its_locks_run_out(fake, monkeypatch):
    configured()
    backups.backup()
    offsite.mirrored()
    old = timezone.localdate().isoformat()
    later = timezone.localdate() + offsite.PERIOD
    monkeypatch.setattr(timezone, "localdate", lambda: later)
    oldest = min(fake.objects[key][1] for key in fake.objects)
    fake.locked = lambda key: key.startswith(old) and fake.objects[key][1] > oldest
    offsite.mirrored()
    new = later.isoformat()
    assert {f"{new}/config", f"{new}.canary"} <= set(fake.objects)
    left = [key for key in fake.objects if key.startswith(old)]
    assert left and len(left) < len([key for key in fake.puts if key.startswith(old)])
    fake.locked = lambda key: False
    offsite.mirrored()
    assert not any(key.startswith(old) for key in fake.objects)


def test_another_installations_repository_in_the_bucket_stops_the_mirror(fake):
    found = configured()
    fake.objects[f"{timezone.localdate().isoformat()}/config"] = (b"other", datetime.now(UTC))
    with pytest.raises(backups.Failed, match="another installation"):
        offsite.mirrored()
    found.refresh_from_db()
    assert "another installation" in found.error


def test_a_damaged_local_file_is_not_copied(fake, tmp_path):
    configured()
    backups.backup()
    pack = next(path for path in (tmp_path / "repository" / "data").rglob("*") if path.is_file())
    pack.chmod(0o600)
    pack.write_bytes(b"damaged")
    with pytest.raises(backups.Failed, match="does not match its name"):
        offsite.mirrored()


@pytest.fixture
def fetched(fake, tmp_path, monkeypatch):
    """The copy in the bucket as restic reads it there, fetched once into a directory."""
    into = tmp_path / "fetched"

    def remote(found):
        if not into.exists():
            into.mkdir()
            target = bucket.Bucket(
                ENDPOINT, NAME, ACCESS, SECRET, transport=httpx2.MockTransport(fake)
            )
            bucket.fetch(target, into)
        return {**os.environ, "RESTIC_REPOSITORY": str(into)}

    monkeypatch.setattr(offsite, "remote", remote)
    monkeypatch.setattr(offsite, "REMOTE", ("--no-lock", "--no-cache"))


def test_the_copy_is_checked_and_restored_on_trial_once_a_day_after_a_mirror(
    fetched, tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    found = configured()
    store.put(io.BytesIO(b"kept bytes"))
    snapshot = backups.backup()
    offsite.mirrored()
    offsite.examined()
    found.refresh_from_db()
    assert (found.check_error, found.trial_error) == ("", "")
    assert found.trial["snapshot"] == snapshot and found.trial["files"] == 1
    checked = found.checked_at
    offsite.examined()
    found.refresh_from_db()
    assert found.checked_at == checked
    assert not list(tmp_path.glob("trial-*"))


def test_a_trial_restore_finds_a_file_the_snapshot_lacks(fetched):
    found = configured()
    Blob.objects.create(
        sha256="0" * 64, size=1, media_type="text/plain", uploaded_at=timezone.now()
    )
    backups.backup()
    offsite.mirrored()
    offsite.examined()
    found.refresh_from_db()
    assert found.check_error == ""
    assert "lacks 1 of the files" in found.trial_error


def test_a_failed_check_is_kept_and_no_trial_follows_it(fetched, monkeypatch):
    found = configured()
    backups.backup()
    offsite.mirrored()

    def damaged(found):
        raise backups.Failed("restic check: pack 1234 is damaged")

    monkeypatch.setattr(offsite, "verify", damaged)
    offsite.examined()
    found.refresh_from_db()
    assert found.check_error == "restic check: pack 1234 is damaged"
    assert found.tried_at is None


def test_the_copy_is_late_once_a_snapshot_waits_too_long_or_the_mirror_fails(fake):
    found = configured()
    now = timezone.now()
    assert offsite.describe(found, None)["late"] is False
    assert offsite.describe(found, now)["late"] is False
    assert offsite.describe(found, now - backups.AGAIN - timedelta(minutes=1))["late"] is True
    found.mirrored_at = now
    assert offsite.describe(found, now - timedelta(hours=2))["late"] is False
    found.error = "unreachable"
    assert offsite.describe(found, None)["late"] is True


def test_the_health_reports_the_offsite_copy(admin, fake, settings, tmp_path):
    settings.CONVERTER_URL = settings.PRINTER_URL = settings.OCR_URL = "http://127.0.0.1:9"
    (tmp_path / "repository").mkdir()
    assert admin.get("/api/health").json()["offsite"] == {"locked": offsite.LOCKED, "setting": None}
    configured()
    described = admin.get("/api/health").json()["offsite"]["setting"]
    assert (described["bucket"], described["hint"], described["protected"]) == (
        NAME,
        SECRET[-4:],
        None,
    )


def test_a_generation_ends_while_the_lock_still_holds_its_first_object():
    assert offsite.PERIOD < timedelta(days=offsite.LOCKED)
