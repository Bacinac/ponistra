"""PONISTRA as the authorization server an MCP client signs in at (D18), as MCP's authorization
specification has it: a client registers itself, sends the user to consent, exchanges the code
for tokens bound to this installation's MCP server, and refreshes them while its grant stands.
The SDK's handlers do the protocol; this is their store, in the installation's database."""

import base64
import hashlib
import hmac
import secrets
from contextvars import ContextVar
from datetime import timedelta
from urllib.parse import unquote

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from mcp.server.auth.middleware.client_auth import AuthenticationError
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl, ValidationError

from apps.core.asyncdb import database

from .models import Authorization, Client, Grant, Token

ACCESS = timedelta(hours=1)
REFRESH = timedelta(days=30)
# How long a sign-in waits for the user's consent, and how long the client has to exchange it.
CONSENT = timedelta(minutes=10)
CODE = timedelta(minutes=5)
# How often a grant's use is noted.
NOTED = timedelta(minutes=10)
# A client that registered but was never let in is forgotten after this.
UNUSED = timedelta(days=1)
# Clients one address may hold registered and not let in by anyone, until UNUSED forgets them.
MOST_UNUSED = 10
CONSENT_PATH = "/agents/consent"


def issuer() -> str:
    return f"{settings.PUBLIC_URL}/api/agents"


def mcp_url() -> str:
    return f"{settings.PUBLIC_URL}/api/mcp"


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _same_resource(given: str | None) -> bool:
    try:
        return str(AnyHttpUrl(given or "")).rstrip("/") == mcp_url()
    except ValidationError:
        return False


def _info(client: Client) -> OAuthClientInformationFull:
    return OAuthClientInformationFull.model_validate(
        {
            **client.registered,
            "client_id": client.client_id,
            "client_secret": client.secret_digest or None,
        }
    )


class Code(AuthorizationCode):
    authorization: str


class Refresh(RefreshToken):
    grant: int


def _sweep(now) -> None:
    Token.objects.filter(expires_at__lt=now).delete()
    Authorization.objects.filter(expires_at__lt=now).delete()
    Client.objects.filter(created_at__lt=now - UNUSED, grants=None, authorizations=None).delete()


registering: ContextVar[str | None] = ContextVar("registering", default=None)


def crowded(address: str | None) -> bool:
    """Whether the address already holds as many clients waiting to be let in as it may."""
    _sweep(timezone.now())
    return Client.objects.filter(address=address, grants=None).count() >= MOST_UNUSED


def _issued(grant: Grant, scopes: list[str]) -> OAuthToken:
    now = timezone.now()
    _sweep(now)
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    Token.objects.bulk_create(
        [
            Token(
                grant=grant,
                kind=Token.Kind.ACCESS,
                digest=digest(access),
                scopes=scopes,
                expires_at=now + ACCESS,
            ),
            Token(
                grant=grant,
                kind=Token.Kind.REFRESH,
                digest=digest(refresh),
                scopes=scopes,
                expires_at=now + REFRESH,
            ),
        ]
    )
    return OAuthToken(
        access_token=access,
        expires_in=int(ACCESS.total_seconds()),
        scope=" ".join(scopes) or None,
        refresh_token=refresh,
    )


def _authorized(client_id: str, params: dict) -> str:
    client = Client.objects.get(client_id=client_id)
    made = Authorization.objects.create(
        client=client, params=params, expires_at=timezone.now() + CONSENT
    )
    return f"{CONSENT_PATH}?request={made.pk}"


def _loaded_code(client_id: str, code: str) -> Code | None:
    found = (
        Authorization.objects.select_related("client")
        .filter(code=code, client__client_id=client_id, used_at=None, user__isnull=False)
        .first()
    )
    if found is None or found.expires_at < timezone.now():
        return None
    params = found.params
    return Code(
        code=code,
        scopes=params.get("scopes") or [],
        expires_at=found.expires_at.timestamp(),
        client_id=client_id,
        code_challenge=params["code_challenge"],
        redirect_uri=params["redirect_uri"],
        redirect_uri_provided_explicitly=params["redirect_uri_provided_explicitly"],
        resource=mcp_url(),
        subject=str(found.user_id),
        authorization=str(found.pk),
    )


def _exchanged_code(code: Code) -> OAuthToken:
    with transaction.atomic():
        taken = (
            Authorization.objects.select_for_update()
            .filter(pk=code.authorization, used_at=None)
            .first()
        )
        if taken is None:
            raise TokenError("invalid_grant", "authorization code already used")
        taken.used_at = timezone.now()
        taken.save(update_fields=["used_at"])
        grant = Grant.objects.filter(client=taken.client, user=taken.user, revoked_at=None).first()
        if grant is None:
            raise TokenError("invalid_grant", "access was revoked")
        return _issued(grant, code.scopes)


def _loaded_refresh(client_id: str, token: str) -> Refresh | None:
    found = (
        Token.objects.select_related("grant__client")
        .filter(kind=Token.Kind.REFRESH, digest=digest(token), grant__client__client_id=client_id)
        .first()
    )
    if found is None or found.expires_at < timezone.now() or found.grant.revoked_at:
        return None
    return Refresh(
        token=token,
        client_id=client_id,
        scopes=found.scopes,
        expires_at=int(found.expires_at.timestamp()),
        resource=mcp_url(),
        subject=str(found.grant.user_id),
        grant=found.grant_id,
    )


def _exchanged_refresh(refresh: Refresh, scopes: list[str]) -> OAuthToken:
    with transaction.atomic():
        if not Token.objects.filter(digest=digest(refresh.token)).delete()[0]:
            raise TokenError("invalid_grant", "refresh token already used")
        grant = Grant.objects.filter(pk=refresh.grant, revoked_at=None).first()
        if grant is None:
            raise TokenError("invalid_grant", "access was revoked")
        return _issued(grant, scopes)


def _loaded_access(token: str) -> AccessToken | None:
    found = (
        Token.objects.select_related("grant__client")
        .filter(kind=Token.Kind.ACCESS, digest=digest(token))
        .first()
    )
    now = timezone.now()
    if found is None or found.expires_at < now or found.grant.revoked_at:
        return None
    grant = found.grant
    if grant.used_at is None or grant.used_at < now - NOTED:
        Grant.objects.filter(pk=grant.pk).update(used_at=now)
    return AccessToken(
        token=token,
        client_id=grant.client.client_id,
        scopes=found.scopes,
        expires_at=int(found.expires_at.timestamp()),
        resource=mcp_url(),
        subject=str(grant.user_id),
        claims={"iss": issuer(), "client_name": grant.client.name, "grant": grant.pk},
    )


class Provider:
    """What the SDK's authorization and token handlers ask of the store, and the verifier of
    the bearer tokens its MCP server reads."""

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        found = await database(Client.objects.filter(client_id=client_id).first)()
        return _info(found) if found else None

    async def register_client(self, info: OAuthClientInformationFull) -> None:
        registered = info.model_dump(
            mode="json", exclude_none=True, exclude={"client_id", "client_secret"}
        )
        await database(Client.objects.create)(
            client_id=info.client_id,
            name=(info.client_name or "").strip()[:200],
            registered=registered,
            secret_digest=digest(info.client_secret) if info.client_secret else "",
            address=registering.get(),
        )

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if params.resource is not None and not _same_resource(params.resource):
            raise AuthorizeError("invalid_target", f"this server is {mcp_url()}")
        given = params.model_dump(mode="json")
        return await database(_authorized)(client.client_id, given)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, code: str
    ) -> Code | None:
        return await database(_loaded_code)(client.client_id, code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, code: Code
    ) -> OAuthToken:
        return await database(_exchanged_code)(code)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, token: str
    ) -> Refresh | None:
        return await database(_loaded_refresh)(client.client_id, token)

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh: Refresh, scopes: list[str]
    ) -> OAuthToken:
        return await database(_exchanged_refresh)(refresh, scopes)

    async def load_access_token(self, token: str) -> AccessToken | None:
        return await database(_loaded_access)(token)

    verify_token = load_access_token

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        await database(Token.objects.filter(digest=digest(token.token)).delete)()


class Authenticator:
    """Who a request to the token or revocation endpoint comes from: the client it names, its
    secret checked against the digest kept, where it registered for one."""

    def __init__(self, provider: Provider):
        self.provider = provider

    async def authenticate_request(self, request) -> OAuthClientInformationFull:
        form = await request.form()
        client_id = form.get("client_id")
        if not isinstance(client_id, str) or not client_id:
            raise AuthenticationError("Missing client_id")
        client = await self.provider.get_client(client_id)
        if client is None:
            raise AuthenticationError("Invalid client_id")
        method = client.token_endpoint_auth_method or "client_secret_post"
        given: str | None = None
        if method == "client_secret_basic":
            header = request.headers.get("Authorization", "")
            try:
                named, _, given = (
                    base64.b64decode(header.removeprefix("Basic ")).decode().partition(":")
                )
            except ValueError, UnicodeDecodeError:
                raise AuthenticationError("Invalid Basic authentication header") from None
            if not header.startswith("Basic ") or unquote(named) != client_id:
                raise AuthenticationError("Client ID mismatch in Basic auth")
            given = unquote(given)
        elif method == "client_secret_post":
            secret = form.get("client_secret")
            given = secret if isinstance(secret, str) else None
        elif method != "none":
            raise AuthenticationError(f"Unsupported auth method: {method}")
        if method != "none":
            if not client.client_secret:
                raise AuthenticationError("Client has no secret")
            if not given or not hmac.compare_digest(client.client_secret, digest(given)):
                raise AuthenticationError("Invalid client_secret")
        return client
