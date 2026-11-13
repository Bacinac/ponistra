"""A folder on a file server of the organisation's network, read over SMB (D37)."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import IO

import smbclient
from smbclient._io import SMB2QueryInfoRequest, SMB2QueryInfoResponse, SMBFileTransaction, SMBRawIO
from smbprotocol import exceptions
from smbprotocol.file_info import FileAttributes, InfoType
from smbprotocol.open import FilePipePrinterAccessMask
from smbprotocol.security_descriptor import (
    AceFlags,
    AceType,
    SDControl,
    SMB2CreateSDBuffer,
)
from spnego.exceptions import SpnegoError

ADDRESS = re.compile(r"^(?:smb:)?[\\/]{2}([^\\/]+)[\\/]+([^\\/]+)((?:[\\/]+[^\\/]+)*)[\\/]*$")
HIDDEN = FileAttributes.FILE_ATTRIBUTE_HIDDEN | FileAttributes.FILE_ATTRIBUTE_SYSTEM
DENIED = {
    AceType.ACCESS_DENIED_ACE_TYPE,
    AceType.ACCESS_DENIED_OBJECT_ACE_TYPE,
    AceType.ACCESS_DENIED_CALLBACK_ACE_TYPE,
    AceType.ACCESS_DENIED_CALLBACK_OBJECT_ACE_TYPE,
}
DACL_SECURITY_INFORMATION = 0x4
IO_REPARSE_TAG_DFS = 0x8000000A
# Postgres indexes a path of at most about 2700 bytes; a share's are kept by their path.
LONGEST = 2000


class Failed(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Address:
    host: str
    path: str

    @property
    def unc(self) -> str:
        return rf"\\{self.host}\{self.path}"


def address_of(given: str) -> Address | None:
    """A folder given as `\\\\server\\share\\folder`, with slashes or as `smb://`."""
    found = ADDRESS.fullmatch(given.strip())
    if found is None:
        return None
    host, share, below = found.groups()
    parts = [share, *(part for part in re.split(r"[\\/]+", below) if part)]
    return Address(host, "\\".join(parts))


@dataclass(frozen=True)
class Found:
    """A file or folder below the connected one, by its path with slashes."""

    path: str
    folder: bool
    size: int
    modified: datetime


@dataclass(frozen=True)
class Left:
    """What stays out, and why: rights narrower than the folder above, a folder the account may
    not read, a link to elsewhere, a path longer than PONISTRA keeps."""

    path: str
    why: str


class Server:
    """A session with the server, its connections its own, closed on leaving."""

    def __init__(self, address: Address, username: str, password: str):
        self.address = address
        self.username = username
        self.password = password
        self.cache: dict = {}

    def __enter__(self) -> Server:
        try:
            smbclient.register_session(
                self.address.host,
                username=self.username,
                password=self.password,
                connection_timeout=15,
                connection_cache=self.cache,
                auth_protocol="ntlm",
            )
            if not smbclient.path.isdir(self.address.unc, connection_cache=self.cache):
                raise Failed("share_not_found")
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        smbclient.reset_connection_cache(connection_cache=self.cache)

    def _full(self, path: str) -> str:
        return "\\".join([self.address.unc, *path.split("/")]) if path else self.address.unc

    def walk(self) -> Iterator[Found | Left]:
        """Every file and folder below, a folder before what it holds; hidden and system files,
        names starting with a dot and Office's owner files left out unsaid."""
        waiting = [""]
        while waiting:
            folder = waiting.pop()
            try:
                entries = list(smbclient.scandir(self._full(folder), connection_cache=self.cache))
            except exceptions.SMBOSError as refused:
                if not folder or not _denied(refused):
                    raise
                yield Left(folder, "unreadable")
                continue
            for entry in sorted(entries, key=lambda each: each.name.casefold()):
                name = entry.name
                info = entry.smb_info
                attributes = info.file_attributes
                if attributes & HIDDEN or name.startswith((".", "~$")):
                    continue
                path = f"{folder}/{name}" if folder else name
                if len(path.encode()) > LONGEST:
                    yield Left(path, "too_long")
                    continue
                is_folder = bool(attributes & FileAttributes.FILE_ATTRIBUTE_DIRECTORY)
                if attributes & FileAttributes.FILE_ATTRIBUTE_REPARSE_POINT and (
                    not is_folder or info.ea_size != IO_REPARSE_TAG_DFS
                ):
                    yield Left(path, "link")
                    continue
                narrower = self.narrower(path)
                if narrower is None:
                    yield Left(path, "unreadable")
                    continue
                if narrower:
                    yield Left(path, "narrower")
                    continue
                yield Found(
                    path,
                    is_folder,
                    0 if is_folder else info.end_of_file,
                    info.last_write_time.replace(tzinfo=UTC),
                )
                if is_folder:
                    waiting.append(path)

    def narrower(self, path: str) -> bool | None:
        """Whether whoever reads the folder above may not read this: its inheritance broken or a
        right denied on it; None where the account may not read its rights."""
        raw = SMBRawIO(
            self._full(path),
            mode="r",
            share_access="rwd",
            desired_access=FilePipePrinterAccessMask.READ_CONTROL,
            connection_cache=self.cache,
        )
        try:
            with SMBFileTransaction(raw) as transaction:
                _query_security(transaction)
        except exceptions.SMBOSError as refused:
            if _denied(refused):
                return None
            raise
        described = transaction.results[0]
        if described["control"].has_flag(SDControl.DACL_PROTECTED):
            return True
        acl = described.get_dacl()
        return acl is not None and any(
            ace["ace_type"].get_value() in DENIED
            and not ace["ace_flags"].has_flag(AceFlags.INHERITED_ACE)
            for ace in acl["aces"].get_value()
        )

    def read(self, path: str, alone: bool = False) -> IO[bytes]:
        """The file's bytes; `alone` refuses while anyone has it open to write, as a scanner
        does until its file is whole."""
        return smbclient.open_file(
            self._full(path),
            mode="rb",
            share_access="r" if alone else "rwd",
            connection_cache=self.cache,
        )

    def deletable(self, path: str) -> bool:
        """Whether the account may delete the file, asked without deleting it."""
        raw = SMBRawIO(
            self._full(path),
            mode="r",
            share_access="rwd",
            desired_access=FilePipePrinterAccessMask.DELETE,
            connection_cache=self.cache,
        )
        try:
            raw.open()
        except exceptions.SMBOSError as refused:
            if _denied(refused):
                return False
            raise
        raw.close()
        return True

    def remove(self, path: str) -> None:
        smbclient.remove(self._full(path), connection_cache=self.cache)


def _query_security(transaction) -> None:
    request = SMB2QueryInfoRequest()
    request["info_type"] = InfoType.SMB2_0_INFO_SECURITY
    request["file_info_class"] = 0
    request["additional_information"] = DACL_SECURITY_INFORMATION
    request["output_buffer_length"] = 65536
    request["file_id"] = transaction.raw.fd.file_id

    def received(sent):
        response = transaction.raw.fd.connection.receive(sent)
        answer = SMB2QueryInfoResponse()
        answer.unpack(response["data"].get_value())
        described = SMB2CreateSDBuffer()
        described.unpack(answer["buffer"].get_value())
        return described

    transaction += (request, received)


def _denied(refused: exceptions.SMBOSError) -> bool:
    return refused.ntstatus == exceptions.NtStatus.STATUS_ACCESS_DENIED


def busy(error: BaseException) -> bool:
    """Whether someone else holds the file open in a way that keeps it from being read now."""
    return (
        isinstance(error, exceptions.SMBOSError)
        and error.ntstatus == exceptions.NtStatus.STATUS_SHARING_VIOLATION
    )


def failure(error: BaseException) -> str | None:
    """The code of what went wrong on the way to the server, None for anything else."""
    if isinstance(error, Failed):
        return error.code
    if isinstance(error, (exceptions.LogonFailure, exceptions.SMBAuthenticationError, SpnegoError)):
        return "share_login"
    if isinstance(error, exceptions.BadNetworkName):
        return "share_not_found"
    if isinstance(error, exceptions.SMBOSError):
        if error.ntstatus in (
            exceptions.NtStatus.STATUS_OBJECT_NAME_NOT_FOUND,
            exceptions.NtStatus.STATUS_OBJECT_PATH_NOT_FOUND,
            exceptions.NtStatus.STATUS_BAD_NETWORK_NAME,
        ):
            return "share_not_found"
        if _denied(error):
            return "share_denied"
    if isinstance(error, (OSError, exceptions.SMBException, ValueError)):
        return "share_unreachable"
    return None
