import os
from datetime import time, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# The reader (apps/reader) runs this code without the installation's secrets, database or files:
# what they would be is empty there, and whatever reaches for one fails.
READER = os.environ.get("PONISTRA_ROLE") == "reader"


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value and not READER:
        raise RuntimeError(f"{name} is not set; see .env.example")
    return value


ENV = required("PONISTRA_ENV")
if ENV not in {"dev", "prod"}:
    raise RuntimeError(f"PONISTRA_ENV must be dev or prod, not {ENV!r}")

DEBUG = ENV == "dev"
SECRET_KEY = required("PONISTRA_SECRET_KEY")
# What the first administrator enters in the browser; ponistra install writes it.
SETUP_CODE = os.environ.get("PONISTRA_SETUP_CODE", "").strip()

if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = [
        "localhost",
        "127.0.0.1",
        # The printer reaches the API through the frontend, by its service name.
        "frontend",
        *(host.strip() for host in required("PONISTRA_ALLOWED_HOSTS").split(",")),
    ]
# Where the installation is reached from outside: what an outside agent, the code workspace's
# among them, is told to sign in at and the resource its tokens are bound to (D18). ponistra
# install writes an installation's; dev's is the Vite the browser check talks to unless .env
# says otherwise.
PUBLIC_URL = (
    (os.environ.get("PONISTRA_PUBLIC_URL", "").strip() or "http://localhost:5173")
    if DEBUG
    else required("PONISTRA_PUBLIC_URL")
).rstrip("/")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.postgres",
    "axes",
    "apps.core",
    "apps.users",
    "apps.blobs",
    "apps.documents",
    "apps.access",
    "apps.collab",
    "apps.content",
    "apps.versions",
    "apps.search",
    "apps.help",
    "apps.comments",
    "apps.imports",
    "apps.exports",
    "apps.actions",
    "apps.ai",
    "apps.jobs",
    "apps.backups",
    "apps.health",
    "apps.journal",
    "apps.retention",
    "apps.mail",
    "apps.agents",
    "apps.identity",
    "apps.contacts",
    "apps.calendar",
    "apps.tasks",
    "apps.chat",
    "apps.meetings",
    "apps.push",
    "apps.dav",
    "apps.vault",
    "apps.engine",
    "apps.workspace",
    "apps.memory",
    "apps.shares",
    "apps.drive",
    "apps.collecting",
]

MIDDLEWARE = [
    "apps.core.answered.answered",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.users.sessions.seen",
    "axes.middleware.AxesMiddleware",
]
if os.environ.get("PONISTRA_MAP"):
    MIDDLEWARE.insert(0, "apps.core.checkmap.marker")

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("POSTGRES_HOST", "postgres"),
        "PORT": "5432",
        "NAME": "ponistra",
        "USER": "ponistra",
        "PASSWORD": required("POSTGRES_PASSWORD"),
        "OPTIONS": {"pool": True},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "apps.identity.backends.Directory",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# TLS ends at Caddy (LAN) or Cloudflare (tunnel); both send X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_ENGINE = "apps.users.sessions"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_HANDLER = "apps.users.throttle.Handler"
# Failures within the cool-off from one address across every account, and at one account from
# the addresses it never signed in from, before either is held as well.
SIGN_IN_ADDRESS_LIMIT = 30
SIGN_IN_ACCOUNT_LIMIT = 30
AXES_RESET_ON_SUCCESS = True
AXES_VERBOSE = False
AXES_CLIENT_IP_CALLABLE = "apps.users.sessions.client_ip"
AXES_LOCKOUT_CALLABLE = "apps.users.views.locked_out"

LANGUAGE_CODE = "hr"
TIME_ZONE = "Europe/Zagreb"
# Where a phone number written without its country code is.
PHONE_REGION = "HR"
USE_I18N = True
USE_TZ = True

BLOB_ROOT = Path("/data/blobs")
# Snapshots take the installation's .env with them: its secret key opens what is sealed with it.
BACKUP_ENV = Path("/installation/.env")
# The night's snapshot, in TIME_ZONE.
BACKUP_AT = time(3)
# The night's pass through the organisations' directories for colleagues, in TIME_ZONE.
CONTACTS_AT = time(4)
# Mail servers reached without TLS: only the test server of a dev or check stack.
MAIL_PLAIN_HOSTS = {
    host.strip()
    for host in os.environ.get("PONISTRA_MAIL_PLAIN_HOSTS", "").split(",")
    if host.strip()
}
FONTS = Path("/fonts/fonts.json")
COLORS = Path("/colors/colors.json")
SCHEMA = Path("/schema/schema.json")
HELP = Path("/help")
I18N = Path("/i18n")
BLOB_MAX_BYTES = int(os.environ.get("PONISTRA_FILE_MAX_GB", "10")) * 1024**3
# The code page CHAR and CODE count characters by, as Excel takes it from Windows.
CODE_PAGE = os.environ.get("PONISTRA_CODE_PAGE", "cp1250")
BLOB_GRACE = timedelta(hours=1)
# A file is uploaded in pieces of this size: Cloudflare refuses a request body over 100 MB.
UPLOAD_CHUNK_BYTES = 32 * 1024 * 1024
UPLOAD_ABANDONED = timedelta(days=1)
# Left free on the disk of the files, which the database and the system write to as well.
UPLOAD_RESERVE_BYTES = 1024**3

CONVERTER_URL = "http://converter:8040"
PRINTER_URL = "http://printer:8050"
OCR_URL = "http://ocr:8060"
READER_URL = "http://reader:8070"
# LiveKit, which carries meetings' sound and video, on the host's own network (compose.yaml).
LIVEKIT_URL = f"http://{required('PONISTRA_LIVEKIT')}"
LIVEKIT_SECRET = required("PONISTRA_LIVEKIT_SECRET")
# Its relay, TURN over TLS on 443 under a name of its own, where the installation has one.
TURN = os.environ.get("PONISTRA_TURN", "").strip()
# The names pointing straight at the installation's public address: the relay's, and the app's
# own where Caddy ends its TLS. Where Cloudflare keeps them, this token (DNS of their zone) keeps
# them on the address as it changes.
DIRECT_NAMES = [
    name
    for name in (TURN, os.environ.get("PONISTRA_SITE", "").strip())
    if name and not name.startswith(":")
]
CLOUDFLARE_TOKEN = os.environ.get("PONISTRA_CLOUDFLARE_TOKEN", "").strip()

# The one user whose code workspace this installation keeps (D34), that workspace's home while it
# runs here, and its address when it runs elsewhere behind a door of its own.
WORKSPACE = os.environ.get("PONISTRA_WORKSPACE", "").strip().lower()
WORKSPACE_ROOT = Path("/data/workspace")
WORKSPACE_TOKEN = os.environ.get("PONISTRA_WORKSPACE_TOKEN", "").strip()
WORKSPACE_URL = os.environ.get("PONISTRA_WORKSPACE_URL", "").strip()
if WORKSPACE_URL and not WORKSPACE_URL.startswith("https://"):
    raise RuntimeError("PONISTRA_WORKSPACE_URL must be https://, as VS Code needs a secure context")

VERSION_QUIET = timedelta(minutes=10)
VERSION_INTERVAL = timedelta(hours=1)
ELEMENT_QUIET = timedelta(seconds=3)
ELEMENT_INTERVAL = timedelta(seconds=30)

SEARCH_SWEEP = timedelta(minutes=5)
BLOB_SWEEP = timedelta(hours=1)
PREVIEW_SWEEP = timedelta(minutes=5)
LINK_SWEEP = timedelta(minutes=5)
SHARE_SWEEP = timedelta(minutes=5)
DRIVE_SWEEP = timedelta(minutes=5)
INBOX_SWEEP = timedelta(seconds=30)
EDITED_QUIET = timedelta(seconds=2)

PAGES_QUIET = timedelta(seconds=10)
PAGES_INTERVAL = timedelta(minutes=1)

JOBS_AT_ONCE = int(os.environ.get("PONISTRA_JOBS_AT_ONCE", "2"))
JOBS_SWEEP = timedelta(minutes=1)
JOBS_KEPT = timedelta(hours=1)

REVISION_FILE = Path(os.environ.get("PONISTRA_REVISION_FILE", BASE_DIR / "revision.json"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"pikepdf": {"level": "WARNING"}, "httpx2": {"level": "WARNING"}},
}
