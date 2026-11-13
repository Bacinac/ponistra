import threading
import time
from contextlib import contextmanager

from django.db import connections, transaction

from apps.blobs.models import Blob


def uploaded(client, data: bytes) -> dict:
    """The Blob that data uploaded in pieces became, as the browser sends them."""
    begun = client.post("/api/uploads", {"size": len(data)}, content_type="application/json")
    assert begun.status_code == 201, begun.json()
    upload = begun.json()
    while upload["blob"] is None:
        offset = upload["received"]
        answer = client.put(
            f"/api/uploads/{upload['id']}",
            data[offset : offset + upload["chunk"]],
            content_type="application/octet-stream",
            headers={"Upload-Offset": str(offset)},
        )
        assert answer.status_code == 200, answer.json()
        upload = answer.json()
    return upload["blob"]


@contextmanager
def held(sha256: str, seconds: float = 0.5):
    """The blob's row held by another transaction for a moment, as the drawer holds a PDF while it
    draws its picture and the extractor while it reads its text."""
    holding = threading.Event()

    def hold():
        try:
            with transaction.atomic():
                Blob.objects.select_for_update(no_key=True).get(pk=sha256)
                holding.set()
                time.sleep(seconds)
        finally:
            connections.close_all()

    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert holding.wait(10)
        yield
    finally:
        thread.join()
