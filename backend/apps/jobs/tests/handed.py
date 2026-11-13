"""Jobs handed over as the browser hands them and done at once, as the queue would do them."""

from apps.jobs import work

JSON = "application/json"


def _handed(client, kind: str, data: dict):
    response = client.post("/api/jobs", {"kind": kind, **data}, content_type=JSON)
    if response.status_code != 202:
        return response, None
    while (claimed := work.claim()) is not None:
        work.run(claimed)
    return response, client.get(f"/api/jobs/{response.json()['id']}").json()


def done(client, kind: str, **data) -> dict:
    """What the job answered."""
    response, job = _handed(client, kind, data)
    assert job is not None, response.json()
    assert job["state"] == "done", job
    return job["answer"]


def saved(client, kind: str, **data):
    """The file the job made, as the browser saves it."""
    response, job = _handed(client, kind, data)
    assert job is not None, response.json()
    assert job["state"] == "done" and job["file"], job
    return client.get(f"/api/jobs/{job['id']}/file?download=1")


def refused(client, kind: str, **data) -> tuple[int, str]:
    """The status and error the job was refused with, as it was handed over or as it was done."""
    response, job = _handed(client, kind, data)
    if job is None:
        return response.status_code, response.json()["error"]
    assert job["state"] == "failed", job
    return job["status"], job["error"]
