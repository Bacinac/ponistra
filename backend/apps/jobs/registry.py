from apps.exports.jobs import KINDS as EXPORTS
from apps.imports.jobs import KINDS as IMPORTS
from apps.mail.jobs import KINDS as MAIL
from apps.meetings.jobs import KINDS as MEETINGS
from apps.users.personal import KINDS as PERSONAL

KINDS = {**EXPORTS, **IMPORTS, **MAIL, **MEETINGS, **PERSONAL}
