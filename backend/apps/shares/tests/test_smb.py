from datetime import UTC, datetime
from types import SimpleNamespace

from smbprotocol.file_info import FileAttributes

from apps.shares import smb


def test_a_file_keeps_the_time_the_server_gives_it(monkeypatch):
    info = SimpleNamespace(
        file_attributes=FileAttributes.FILE_ATTRIBUTE_ARCHIVE,
        ea_size=0,
        end_of_file=6,
        last_write_time=datetime(2026, 11, 9, 8, 4, 33),
    )
    monkeypatch.setattr(
        smb.smbclient,
        "scandir",
        lambda *_, **__: [SimpleNamespace(name="plan.txt", smb_info=info)],
    )
    monkeypatch.setattr(smb.Server, "narrower", lambda *_: False)
    server = smb.Server(smb.Address("host", "share"), "user", "secret")

    assert list(server.walk()) == [
        smb.Found("plan.txt", False, 6, datetime(2026, 11, 9, 8, 4, 33, tzinfo=UTC))
    ]
