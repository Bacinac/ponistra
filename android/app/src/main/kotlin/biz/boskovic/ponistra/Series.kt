package biz.boskovic.ponistra

import android.provider.CalendarContract.Attendees
import android.provider.CalendarContract.Events
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/** Someone asked to a meeting as PONISTRA keeps them: status needs-action, accepted, tentative or
 *  declined; role required, optional, chair or informed. */
data class Attendee(val email: String, val name: String, val status: String, val role: String)

/** A part of a series as PONISTRA gives it: the master (no recurrence id) or one occurrence
 *  changed on its own, at the start the series gave it. Instants are epoch milliseconds; an
 *  all-day part's are its days at midnight UTC, the end exclusive, as Android holds them. */
data class Part(
    val recurrenceId: Long?,
    val summary: String,
    val location: String,
    val description: String,
    val allDay: Boolean,
    val starts: Long,
    val ends: Long,
    val zone: String,
    val rrule: String,
    val rdates: List<Long>,
    val exdates: List<Long>,
    val status: String,
    val busy: Boolean,
    val private: Boolean,
    val organizer: String,
    val attendees: List<Attendee>,
    val reminders: List<Int>,
    val response: String,
    val dayOff: String,
)

/** A part of a series as a row of the phone's calendar provider and back (D26). The row of a
 *  part keeps in SYNC_DATA2 how PONISTRA's way with days off treats it, which only PONISTRA
 *  reads. */
object Series {
    const val DAY_OFF = Events.SYNC_DATA2
    const val MOVED = "moved"
    private const val UTC = "UTC"
    private const val DAY = 24 * 60 * 60 * 1000L
    private val STAMP = DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'").withZone(ZoneOffset.UTC)
    private val DATE = DateTimeFormatter.BASIC_ISO_DATE
    private val LOCAL = DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss")
    private val DURATION = Regex("""([+-])?P(?:(\d+)W)?(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?""")
    private val STATUSES = mapOf(
        "confirmed" to Events.STATUS_CONFIRMED,
        "tentative" to Events.STATUS_TENTATIVE,
        "cancelled" to Events.STATUS_CANCELED,
    )
    private val ANSWERS = mapOf(
        "accepted" to Attendees.ATTENDEE_STATUS_ACCEPTED,
        "declined" to Attendees.ATTENDEE_STATUS_DECLINED,
        "tentative" to Attendees.ATTENDEE_STATUS_TENTATIVE,
        "needs-action" to Attendees.ATTENDEE_STATUS_INVITED,
    )
    private val ROLES = mapOf(
        "optional" to Attendees.TYPE_OPTIONAL,
        "informed" to Attendees.TYPE_NONE,
    )

    /** The columns of the part's row, each to be written even where empty, so a value PONISTRA
     *  dropped leaves the row too. Android repeats a series by its DURATION and wants no DTEND;
     *  it keeps HAS_ALARM by the reminders itself and refuses the user's own answer on a row that
     *  exists (`inserted`). */
    fun values(part: Part, owner: String): Map<String, Any?> {
        val repeated = part.recurrenceId == null && (part.rrule.isNotEmpty() || part.rdates.isNotEmpty())
        return mapOf(
            Events.TITLE to part.summary,
            Events.EVENT_LOCATION to part.location,
            Events.DESCRIPTION to part.description,
            Events.ALL_DAY to if (part.allDay) 1 else 0,
            Events.DTSTART to part.starts,
            Events.DTEND to if (repeated) null else part.ends,
            Events.DURATION to if (repeated) duration(part) else null,
            Events.EVENT_TIMEZONE to if (part.allDay) UTC else part.zone.ifEmpty { UTC },
            Events.EVENT_END_TIMEZONE to null,
            Events.RRULE to part.rrule.takeIf { part.recurrenceId == null && it.isNotEmpty() },
            Events.RDATE to dates(part.rdates.takeIf { part.recurrenceId == null }.orEmpty()),
            Events.EXDATE to dates(part.exdates.takeIf { part.recurrenceId == null }.orEmpty()),
            Events.ORIGINAL_INSTANCE_TIME to part.recurrenceId,
            Events.ORIGINAL_ALL_DAY to if (part.recurrenceId == null) null else if (part.allDay) 1 else 0,
            Events.STATUS to (STATUSES[part.status] ?: Events.STATUS_CONFIRMED),
            Events.AVAILABILITY to if (part.busy) Events.AVAILABILITY_BUSY else Events.AVAILABILITY_FREE,
            Events.ACCESS_LEVEL to if (part.private) Events.ACCESS_PRIVATE else Events.ACCESS_DEFAULT,
            Events.ORGANIZER to part.organizer.ifEmpty { owner },
            Events.HAS_ATTENDEE_DATA to 1,
            DAY_OFF to part.dayOff,
        )
    }

    /** The columns of a new row of the part, which alone takes the user's own answer. */
    fun inserted(part: Part, owner: String): Map<String, Any?> =
        values(part, owner) + (Events.SELF_ATTENDEE_STATUS to answer(part))

    /** The user's own answer as the row holds it. */
    fun answer(part: Part): Int = ANSWERS[part.response] ?: Attendees.ATTENDEE_STATUS_NONE

    /** The columns of an attendee's row. */
    fun attendee(attendee: Attendee): Map<String, Any?> = mapOf(
        Attendees.ATTENDEE_EMAIL to attendee.email,
        Attendees.ATTENDEE_NAME to attendee.name,
        Attendees.ATTENDEE_STATUS to (ANSWERS[attendee.status] ?: Attendees.ATTENDEE_STATUS_NONE),
        Attendees.ATTENDEE_TYPE to (ROLES[attendee.role] ?: Attendees.TYPE_REQUIRED),
        Attendees.ATTENDEE_RELATIONSHIP to Attendees.RELATIONSHIP_ATTENDEE,
    )

    /** The columns `part` reads of a row. */
    val COLUMNS = arrayOf(
        Events.TITLE, Events.EVENT_LOCATION, Events.DESCRIPTION, Events.ALL_DAY, Events.DTSTART, Events.DTEND,
        Events.DURATION, Events.EVENT_TIMEZONE, Events.RRULE, Events.RDATE, Events.EXDATE, Events.ORIGINAL_INSTANCE_TIME,
        Events.STATUS, Events.AVAILABILITY, Events.ACCESS_LEVEL, Events.ORGANIZER, Events.SELF_ATTENDEE_STATUS, DAY_OFF,
    )

    /** The part a row of the phone holds, with its attendees and reminders. */
    fun part(row: Map<String, String?>, attendees: List<Attendee>, reminders: List<Int>, owner: String): Part {
        val allDay = row[Events.ALL_DAY] == "1"
        val starts = row[Events.DTSTART]?.toLongOrNull() ?: 0
        val ends = row[Events.DTEND]?.toLongOrNull() ?: (starts + (lasting(row[Events.DURATION]) ?: if (allDay) DAY else 0))
        val recurrenceId = row[Events.ORIGINAL_INSTANCE_TIME]?.toLongOrNull()
        val organizer = row[Events.ORGANIZER].orEmpty()
        return Part(
            recurrenceId = recurrenceId,
            summary = row[Events.TITLE].orEmpty(),
            location = row[Events.EVENT_LOCATION].orEmpty(),
            description = row[Events.DESCRIPTION].orEmpty(),
            allDay = allDay,
            starts = starts,
            ends = maxOf(ends, starts),
            zone = if (allDay) "" else row[Events.EVENT_TIMEZONE].orEmpty(),
            rrule = if (recurrenceId == null) row[Events.RRULE].orEmpty() else "",
            rdates = if (recurrenceId == null) datesOf(row[Events.RDATE]) else emptyList(),
            exdates = if (recurrenceId == null) datesOf(row[Events.EXDATE]) else emptyList(),
            status = STATUSES.entries.firstOrNull { "${it.value}" == row[Events.STATUS] }?.key ?: "confirmed",
            busy = row[Events.AVAILABILITY] != "${Events.AVAILABILITY_FREE}",
            private = row[Events.ACCESS_LEVEL] in setOf("${Events.ACCESS_PRIVATE}", "${Events.ACCESS_CONFIDENTIAL}"),
            organizer = if (organizer.equals(owner, ignoreCase = true)) "" else organizer,
            attendees = attendees,
            reminders = reminders.filter { it >= 0 }.distinct().sorted(),
            response = ANSWERS.entries.firstOrNull { "${it.value}" == row[Events.SELF_ATTENDEE_STATUS] }?.key.orEmpty(),
            dayOff = row[DAY_OFF].orEmpty(),
        )
    }

    /** An attendee as the phone's row holds them. */
    fun attendeeOf(row: Map<String, String?>): Attendee = Attendee(
        email = row[Attendees.ATTENDEE_EMAIL].orEmpty().trim().lowercase(),
        name = row[Attendees.ATTENDEE_NAME].orEmpty().trim(),
        status = ANSWERS.entries.firstOrNull { "${it.value}" == row[Attendees.ATTENDEE_STATUS] }?.key ?: "needs-action",
        role = ROLES.entries.firstOrNull { "${it.value}" == row[Attendees.ATTENDEE_TYPE] }?.key ?: "required",
    )

    /** RDATEs or EXDATEs as Android keeps them: UTC instants, comma-separated. */
    fun dates(given: List<Long>): String? =
        given.takeIf { it.isNotEmpty() }?.joinToString(",") { STAMP.format(Instant.ofEpochMilli(it)) }

    /** RDATEs or EXDATEs as a calendar app may have written them: lines, each with a zone before
     *  a semicolon or none for UTC, of dates, local times or UTC times. */
    fun datesOf(text: String?): List<Long> = text.orEmpty().split("\n").filter { it.isNotBlank() }.flatMap { line ->
        val zone = if (";" in line) zoneOf(line.substringBefore(";")) else ZoneOffset.UTC
        line.substringAfter(";").split(",").mapNotNull { instantOf(it.trim(), zone) }
    }

    /** How long the part lasts as Android writes a DURATION: whole days for an all-day part. */
    fun duration(part: Part): String {
        val lasting = maxOf(part.ends - part.starts, 0)
        return if (part.allDay && lasting % DAY == 0L) "P${lasting / DAY}D" else "P${lasting / 1000}S"
    }

    /** A DURATION in milliseconds; null where it is none. */
    fun lasting(text: String?): Long? {
        val found = DURATION.matchEntire(text?.trim()?.uppercase() ?: return null) ?: return null
        val (sign, weeks, days, hours, minutes, seconds) = found.destructured
        val total = (weeks.toLongOrNull() ?: 0) * 7 * DAY + (days.toLongOrNull() ?: 0) * DAY +
            (hours.toLongOrNull() ?: 0) * 3_600_000 + (minutes.toLongOrNull() ?: 0) * 60_000 +
            (seconds.toLongOrNull() ?: 0) * 1000
        return if (sign == "-") -total else total
    }

    private fun zoneOf(name: String): ZoneId = try {
        ZoneId.of(name.trim().removePrefix("TZID="))
    } catch (_: java.time.DateTimeException) {
        ZoneOffset.UTC
    }

    private fun instantOf(value: String, zone: ZoneId): Long? = try {
        when {
            value.length == 8 -> LocalDate.parse(value, DATE).atStartOfDay(zone).toInstant().toEpochMilli()
            value.endsWith("Z") -> LocalDateTime.parse(value.dropLast(1), LOCAL).toInstant(ZoneOffset.UTC).toEpochMilli()
            else -> LocalDateTime.parse(value, LOCAL).atZone(zone).toInstant().toEpochMilli()
        }
    } catch (_: java.time.format.DateTimeParseException) {
        null
    }
}
