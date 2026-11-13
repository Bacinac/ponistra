"""How an account signs in to its servers (D15, S3-4): with its password, or through OAuth with
the installation's own client at Google or Microsoft, the refresh token kept sealed as the
account's secret and a current access token given to IMAP and SMTP through XOAUTH2."""

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from logging import getLogger

from apps.core import sealed

from .imap import Failed, Login
from .models import Account, Client, Provider, Security

TIMEOUT = 20
# An access token is renewed this long before it ends, and a connection that signed in with it
# ends first: Exchange Online drops an IMAP session whose token has run out.
EARLY = 10 * 60
# Microsoft's tenant of personal accounts (Outlook.com), whose sending server has its own name.
CONSUMERS = "9188040d-6c67-4c5b-b112-36a304b66dad"
CLIENT_ERRORS = {"invalid_client", "unauthorized_client"}
MAIL, GRAPH = "mail", "graph"
log = getLogger(__name__)


@dataclass(frozen=True)
class Way:
    authorize: str
    token: str
    scope: str
    asked: dict
    imap: tuple[str, int, str]
    smtp: tuple[str, int, str]
    # A code that cannot be good, traded to learn whether the provider knows the client.
    probe: str
    # Consented to at the same sign-in, but Microsoft gives a token for one resource at a time, so
    # the mail's token is asked for by its own scope.
    beside: str = ""


WAYS = {
    Provider.GOOGLE: Way(
        authorize="https://accounts.google.com/o/oauth2/v2/auth",
        token="https://oauth2.googleapis.com/token",
        scope=" ".join(
            [
                "https://mail.google.com/",
                "https://www.googleapis.com/auth/carddav",
                # Restricted, yet unverified for an Internal consent screen of the organisation's
                # own Workspace, where its people take their Drive with them (D44).
                "https://www.googleapis.com/auth/drive.readonly",
                "openid email",
            ]
        ),
        # Google gives a refresh token only when the user is asked to consent.
        asked={"access_type": "offline", "prompt": "consent"},
        imap=("imap.gmail.com", 993, Security.TLS),
        smtp=("smtp.gmail.com", 465, Security.TLS),
        probe="ponistra-check",
    ),
    Provider.MICROSOFT: Way(
        authorize="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        scope=" ".join(
            [
                "https://outlook.office.com/IMAP.AccessAsUser.All",
                "https://outlook.office.com/SMTP.Send",
                "offline_access openid email",
            ]
        ),
        asked={"prompt": "select_account"},
        imap=("outlook.office365.com", 993, Security.TLS),
        smtp=("smtp.office365.com", 587, Security.STARTTLS),
        # Microsoft calls a code not shaped like its own malformed before it looks at the client.
        probe="M.C534_BAY.2.U.ponistra-check",
        beside="https://graph.microsoft.com/Calendars.Read https://graph.microsoft.com/Contacts.Read",
    ),
}
PERSONAL_SMTP = ("smtp-mail.outlook.com", 587, Security.STARTTLS)


@dataclass(frozen=True)
class Granted:
    """What the provider gave for the account the user signed in with."""

    address: str
    refresh: str
    access: str
    imap: tuple[str, int, str]
    smtp: tuple[str, int, str]


_tokens: dict[tuple[int, str], tuple[str, float]] = {}
_lock = threading.Lock()


def client(provider: str) -> tuple[str, str]:
    """The installation's client ID and secret at the provider."""
    found = Client.objects.filter(provider=provider).first()
    secret = found and sealed.opened("oauth client", found.secret)
    if not secret:
        raise Failed("oauth_client")
    return found.client_id, secret


def ready() -> list[str]:
    """The providers an account can sign in through: those whose client the installation has."""
    found = Client.objects.order_by("provider")
    return [each.provider for each in found if sealed.opened("oauth client", each.secret)]


def _scope(provider: str, resource: str = MAIL) -> dict:
    """The scope a token for the resource is asked for by, where the provider gives one token for
    every resource the user consented to only if none is named."""
    way = WAYS[provider]
    if resource == GRAPH:
        return {"scope": f"{way.beside} offline_access"}
    return {"scope": way.scope} if way.beside else {}


def _token(provider: str, client_id: str, secret: str, **form) -> dict:
    data = urllib.parse.urlencode({"client_id": client_id, "client_secret": secret, **form})
    request = urllib.request.Request(
        WAYS[provider].token, data=data.encode(), headers={"Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as refused:
        try:
            answer = json.load(refused)
            error, why = answer.get("error", ""), answer.get("error_description", "")
        except ValueError, AttributeError:
            error = why = ""
        if error in CLIENT_ERRORS:
            log.warning("mail: %s refused the installation's client: %s", provider, why)
            raise Failed("oauth_client") from None
        # A refresh token the user withdrew, or one the provider ended, as on a password change.
        raise Failed("oauth_login" if error == "invalid_grant" else "oauth_refused") from None
    except OSError, ValueError:
        raise Failed("oauth_unreachable") from None


def checked(provider: str, client_id: str, secret: str, redirect: str) -> None:
    """Asks the provider whether it knows the client, by trading a code that cannot be good: a
    client it knows is told the code is wrong."""
    try:
        _token(
            provider,
            client_id,
            secret,
            grant_type="authorization_code",
            code=WAYS[provider].probe,
            redirect_uri=redirect,
        )
    except Failed as failed:
        if failed.code in {"oauth_client", "oauth_unreachable"}:
            raise


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def started(provider: str, redirect: str, hint: str = "") -> tuple[str, dict]:
    """The provider's page the user signs in on, and what the way back needs kept meanwhile."""
    client_id, _ = client(provider)
    way = WAYS[provider]
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(64)
    query = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": f"{way.scope} {way.beside}".strip(),
        "state": state,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        **way.asked,
    }
    if hint:
        query["login_hint"] = hint
    kept = {"state": state, "verifier": verifier, "redirect": redirect}
    return f"{way.authorize}?{urllib.parse.urlencode(query)}", kept


def _claims(id_token: str) -> dict:
    """The ID token's claims. It came straight from the provider's token endpoint over TLS, which
    OpenID Connect lets stand for checking its signature."""
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except IndexError, ValueError:
        raise Failed("oauth_refused") from None
    if not isinstance(claims, dict):
        raise Failed("oauth_refused")
    return claims


def granted(provider: str, code: str, verifier: str, redirect: str) -> Granted:
    """Trades the code the user came back with for the account's tokens and address."""
    client_id, secret = client(provider)
    answer = _token(
        provider,
        client_id,
        secret,
        grant_type="authorization_code",
        code=code,
        code_verifier=verifier,
        redirect_uri=redirect,
        **_scope(provider),
    )
    claims = _claims(str(answer.get("id_token", "")))
    address = str(claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    refresh, access = answer.get("refresh_token"), answer.get("access_token")
    if claims.get("aud") != client_id or "@" not in address or not refresh or not access:
        raise Failed("oauth_refused")
    way = WAYS[provider]
    personal = provider == Provider.MICROSOFT and claims.get("tid") == CONSUMERS
    return Granted(address, refresh, access, way.imap, PERSONAL_SMTP if personal else way.smtp)


def forget(account: Account) -> None:
    with _lock:
        for resource in (MAIL, GRAPH):
            _tokens.pop((account.pk, resource), None)


def _access(account: Account, resource: str = MAIL) -> tuple[str, float]:
    """A current access token for the resource and when it ends. Microsoft replaces the refresh
    token at each use without ending the old one, and the new one is kept."""
    with _lock:
        found = _tokens.get((account.pk, resource))
    if found and found[1] - EARLY > time.time():
        return found
    secret = Account.objects.filter(pk=account.pk).values_list("secret", flat=True).first()
    refresh = secret and sealed.opened("mail", secret)
    if not refresh:
        raise Failed("mail_lost")
    client_id, client_secret = client(account.login)
    answer = _token(
        account.login,
        client_id,
        client_secret,
        grant_type="refresh_token",
        refresh_token=refresh,
        **_scope(account.login, resource),
    )
    if not answer.get("access_token"):
        raise Failed("oauth_refused")
    if (renewed := answer.get("refresh_token")) and renewed != refresh:
        Account.objects.filter(pk=account.pk).update(secret=sealed.seal("mail", renewed))
    found = (answer["access_token"], time.time() + int(answer.get("expires_in", 3600)))
    with _lock:
        _tokens[account.pk, resource] = found
    return found


def graph(account: Account) -> str:
    """A current access token for Microsoft Graph, which the account consented to at its
    sign-in."""
    if account.login != Account.Login.MICROSOFT:
        raise Failed("oauth_refused")
    return _access(account, GRAPH)[0]


def drive(account: Account) -> str:
    """A current access token for Google Drive, which the account consented to at its sign-in."""
    if account.login != Account.Login.GOOGLE:
        raise Failed("oauth_refused")
    return _access(account)[0]


def password(account: Account) -> str:
    found = sealed.opened("mail", account.secret)
    if found is None:
        raise Failed("mail_lost")
    return found


def login(account: Account) -> tuple[Login, float | None]:
    """How the account signs in now, and the moment a connection that signed in so must end."""
    if account.login == Account.Login.PASSWORD:
        return Login(account.username, password=password(account)), None
    access, ends = _access(account)
    return Login(account.username, token=access), ends - EARLY
