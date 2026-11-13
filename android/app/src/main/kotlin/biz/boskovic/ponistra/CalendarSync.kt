package biz.boskovic.ponistra

import android.Manifest
import android.accounts.Account
import android.accounts.AccountManager
import android.app.Service
import android.content.AbstractThreadedSyncAdapter
import android.content.ContentProviderClient
import android.content.ContentProviderOperation
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.SyncResult
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.IBinder
import android.provider.CalendarContract
import android.provider.CalendarContract.Attendees
import android.provider.CalendarContract.Calendars
import android.provider.CalendarContract.Events
import android.provider.CalendarContract.Reminders
import android.util.Log
import java.util.Locale
import java.util.UUID
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject

/** The user's PONISTRA calendars in the phone's own Calendar app through the account the phone
 *  connected with (D26): their own both ways, an organisation's read only. PONISTRA holds the
 *  truth: a series the phone changed that changed there meanwhile gives way to PONISTRA's. */
object CalendarSync : PhoneSync(
    CalendarContract.AUTHORITY,
    arrayOf(Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR),
    2,
    "calendar",
    R.string.calendar_channel,
    R.string.calendar_refused_title,
    R.string.calendar_refused_text,
)

class CalendarSyncAdapter(context: Context) : AbstractThreadedSyncAdapter(context, false) {
    override fun onPerformSync(
        account: Account,
        extras: Bundle,
        authority: String,
        provider: ContentProviderClient,
        result: SyncResult,
    ) = CalendarSync.performed(context, account, result) { origin, password ->
        Diary(account, provider, origin, password, result).sync()
    }
}

class CalendarSyncService : Service() {
    private val adapter by lazy { CalendarSyncAdapter(applicationContext) }

    override fun onBind(intent: Intent?): IBinder? = adapter.syncAdapterBinder
}

/** One sync of an account's calendars: the calendars PONISTRA lists come to the phone and those
 *  it no longer lists go; then, calendar by calendar, what the phone deleted and changed goes up
 *  and what changed in PONISTRA since the revision the phone read last comes down. A calendar's
 *  _SYNC_ID is its id in PONISTRA, CAL_SYNC1 the colour PONISTRA gave it (the user's own colour
 *  stays until PONISTRA's changes), CAL_SYNC2 the revision the phone read last. A series is its
 *  master's row and a row for each occurrence changed on its own: its href (its name in the
 *  calendar) is the master's _SYNC_ID, and the master's SYNC_DATA1 the revision the phone has. */
private class Diary(
    private val account: Account,
    private val provider: ContentProviderClient,
    private val origin: String,
    private val password: String,
    private val result: SyncResult,
) {
    private class Held(val id: Long, val color: String?, val since: Long)

    private class Shelf(val id: Long, val pk: Long, val owner: String, val readOnly: Boolean, val since: Long)

    private class Local(
        val id: Long,
        val href: String?,
        val original: Long?,
        val revision: Long?,
        val dirty: Boolean,
        val deleted: Boolean,
        val row: Map<String, String?>,
    )

    private val root: HttpUrl = "$origin/api/device/calendars".toHttpUrl()
    private val language = if (Locale.getDefault().language == "hr") "hr" else "en"

    fun sync() {
        val served = call(Request.Builder().url(root).get()).use { answer ->
            if (!answer.isSuccessful) throw unexpected(answer)
            JSONObject(answer.body.string()).getJSONArray("calendars")
        }
        val held = calendars()
        val listed = mutableSetOf<Long>()
        for (at in 0 until served.length()) {
            val calendar = served.getJSONObject(at)
            listed += calendar.getLong("id")
            synced(kept(calendar, held[calendar.getLong("id")]), calendar.getLong("revision"))
        }
        for ((pk, local) in held) {
            if (pk !in listed) provider.delete(adapted(ContentUris.withAppendedId(Calendars.CONTENT_URI, local.id)), null, null)
        }
    }

    private fun calendars(): Map<Long, Held> {
        val found = mutableMapOf<Long, Held>()
        provider.query(
            adapted(Calendars.CONTENT_URI),
            arrayOf(Calendars._ID, Calendars._SYNC_ID, Calendars.CAL_SYNC1, Calendars.CAL_SYNC2),
            "${Calendars.ACCOUNT_NAME}=? AND ${Calendars.ACCOUNT_TYPE}=?",
            arrayOf(account.name, account.type),
            null,
        )?.use { rows ->
            while (rows.moveToNext()) {
                val pk = rows.getString(1)?.toLongOrNull() ?: continue
                found[pk] = Held(rows.getLong(0), rows.getString(2), rows.getString(3)?.toLongOrNull() ?: 0)
            }
        }
        return found
    }

    /** The calendar's row as PONISTRA lists it, made where the phone has none. */
    private fun kept(calendar: JSONObject, held: Held?): Shelf {
        val pk = calendar.getLong("id")
        val color = calendar.getString("color")
        val readOnly = calendar.getBoolean("read_only")
        val owner = calendar.getString("owner")
        val values = ContentValues().apply {
            put(Calendars.CALENDAR_DISPLAY_NAME, calendar.getString("name"))
            put(Calendars.CALENDAR_ACCESS_LEVEL, if (readOnly) Calendars.CAL_ACCESS_READ else Calendars.CAL_ACCESS_OWNER)
            put(Calendars.OWNER_ACCOUNT, owner)
            put(Calendars.ALLOWED_REMINDERS, "${Reminders.METHOD_DEFAULT},${Reminders.METHOD_ALERT}")
            put(Calendars.ALLOWED_AVAILABILITY, "${Events.AVAILABILITY_BUSY},${Events.AVAILABILITY_FREE}")
            put(
                Calendars.ALLOWED_ATTENDEE_TYPES,
                "${Attendees.TYPE_NONE},${Attendees.TYPE_REQUIRED},${Attendees.TYPE_OPTIONAL}",
            )
            if (held?.color != color) {
                put(Calendars.CALENDAR_COLOR, Color.parseColor(color))
                put(Calendars.CAL_SYNC1, color)
            }
        }
        if (held != null) {
            provider.update(adapted(ContentUris.withAppendedId(Calendars.CONTENT_URI, held.id)), values, null, null)
            return Shelf(held.id, pk, owner, readOnly, held.since)
        }
        values.apply {
            put(Calendars.ACCOUNT_NAME, account.name)
            put(Calendars.ACCOUNT_TYPE, account.type)
            put(Calendars._SYNC_ID, "$pk")
            put(Calendars.NAME, "ponistra-$pk")
            put(Calendars.VISIBLE, 1)
            put(Calendars.SYNC_EVENTS, 1)
            put(Calendars.CAL_SYNC2, "0")
        }
        return Shelf(ContentUris.parseId(provider.insert(adapted(Calendars.CONTENT_URI), values)!!), pk, owner, readOnly, 0)
    }

    /** What the phone changed goes up, then what PONISTRA changed comes down: the whole calendar
     *  where PONISTRA refused one of the phone's changes, to take its own back. */
    private fun synced(shelf: Shelf, revision: Long) {
        var whole = false
        if (shelf.readOnly) {
            whole = locals(shelf).any { it.dirty || it.deleted }
        } else {
            folded(shelf)
            val locals = locals(shelf).filter { it.original == null }
            for (local in locals.filter { it.deleted }) whole = removed(shelf, local) || whole
            for (local in locals.filter { it.dirty && !it.deleted }) whole = changed(shelf, local) || whole
        }
        if (whole) read(shelf, 0) else if (revision != shelf.since) read(shelf, shelf.since)
    }

    private fun locals(shelf: Shelf): List<Local> {
        val found = mutableListOf<Local>()
        val head = arrayOf(Events._ID, Events._SYNC_ID, Events.ORIGINAL_ID, Events.SYNC_DATA1, Events.DIRTY, Events.DELETED)
        provider.query(adapted(Events.CONTENT_URI), head + Series.COLUMNS, "${Events.CALENDAR_ID}=?", arrayOf("${shelf.id}"), null)
            ?.use { rows ->
                while (rows.moveToNext()) {
                    found += Local(
                        rows.getLong(0),
                        rows.getString(1),
                        if (rows.isNull(2)) null else rows.getLong(2),
                        rows.getString(3)?.toLongOrNull(),
                        rows.getInt(4) != 0,
                        rows.getInt(5) != 0,
                        Series.COLUMNS.withIndex().associate { (at, column) -> column to rows.getString(at + head.size) },
                    )
                }
            }
        return found
    }

    /** An occurrence the phone changed or deleted on its own makes its series changed: one it
     *  deleted leaves the series as an exception, one it changed is the user's from then on,
     *  even where PONISTRA had moved it for a day off. */
    private fun folded(shelf: Shelf) {
        val locals = locals(shelf)
        val masters = locals.filter { it.original == null }.associateBy { it.id }
        val touched = locals.filter { it.original != null && (it.dirty || it.deleted) }
        for ((original, occurrences) in touched.groupBy { it.original }) {
            val operations = arrayListOf<ContentProviderOperation>()
            masters[original]?.let { master ->
                val gone = occurrences.filter { it.deleted }.mapNotNull { it.row[Events.ORIGINAL_INSTANCE_TIME]?.toLongOrNull() }
                operations += ContentProviderOperation.newUpdate(adapted(ContentUris.withAppendedId(Events.CONTENT_URI, master.id)))
                    .withValue(Events.DIRTY, 1)
                    .apply {
                        if (gone.isNotEmpty()) {
                            withValue(Events.EXDATE, Series.dates((Series.datesOf(master.row[Events.EXDATE]) + gone).distinct()))
                        }
                    }
                    .build()
            }
            for (local in occurrences) {
                val row = adapted(ContentUris.withAppendedId(Events.CONTENT_URI, local.id))
                operations += if (local.deleted) {
                    ContentProviderOperation.newDelete(row).build()
                } else {
                    ContentProviderOperation.newUpdate(row)
                        .withValue(Events.DIRTY, 0)
                        .apply { if (local.row[Series.DAY_OFF] == Series.MOVED) withValue(Series.DAY_OFF, "") }
                        .build()
                }
            }
            provider.applyBatch(operations)
        }
    }

    /** Deletes in PONISTRA a series the phone deleted; whether PONISTRA refused, so the whole
     *  calendar must be read again to bring it back. */
    private fun removed(shelf: Shelf, local: Local): Boolean {
        var whole = false
        if (local.href != null && local.revision != null) {
            val url = series(shelf, local.href).newBuilder()
                .addQueryParameter("revision", "${local.revision}")
                .addQueryParameter("language", language)
                .build()
            call(Request.Builder().url(url).delete()).use { answer ->
                if (answer.code !in setOf(204, 403, 404, 412)) throw unexpected(answer)
                whole = answer.code in setOf(403, 412)
            }
        }
        dropped(local.id)
        return whole
    }

    /** Sends a series the phone changed; whether PONISTRA refused it, so the whole calendar must be
     *  read again to take PONISTRA's. */
    private fun changed(shelf: Shelf, local: Local): Boolean {
        val occurrences = locals(shelf).filter { it.original == local.id && !it.deleted }
        val parts = (listOf(local) + occurrences).map { Series.part(it.row, attendees(it.id), reminders(it.id), shelf.owner) }
        val href = local.href ?: "${UUID.randomUUID()}.ics".also { named(local.id, it) }
        val sent = JSONObject()
            .put("revision", local.revision ?: JSONObject.NULL)
            .put("language", language)
            .put("parts", JSONArray(parts.map(::partJson)))
        call(Request.Builder().url(series(shelf, href)).put(sent.toString().toRequestBody(JSON))).use { answer ->
            when (answer.code) {
                200, 201 -> {
                    applied(shelf, JSONObject(answer.body.string()), local)
                    result.stats.numUpdates++
                }
                403, 412 -> return true
                404 -> dropped(local.id)
                400 -> {
                    Log.w(TAG, "$origin refused the event $href: ${answer.body.string()}")
                    result.stats.numParseExceptions++
                }
                else -> throw unexpected(answer)
            }
        }
        return false
    }

    private fun read(shelf: Shelf, since: Long) {
        val url = root.newBuilder().addPathSegment("${shelf.pk}").addQueryParameter("since", "$since").build()
        val given = call(Request.Builder().url(url).get()).use { answer ->
            if (answer.code == 410 && since > 0) return read(shelf, 0)
            if (!answer.isSuccessful) throw unexpected(answer)
            JSONObject(answer.body.string())
        }
        val locals = locals(shelf).filter { it.original == null && it.href != null }.associateBy { it.href!! }
        val events = given.getJSONArray("events")
        val listed = mutableSetOf<String>()
        for (at in 0 until events.length()) {
            val served = events.getJSONObject(at)
            val href = served.getString("href")
            listed += href
            val local = locals[href]
            applied(shelf, served, local)
            if (local == null) result.stats.numInserts++ else result.stats.numUpdates++
        }
        val gone = given.getJSONArray("gone").let { array -> (0 until array.length()).map(array::getString) }
        val dropped = if (since == 0L) locals.keys - listed else gone.toSet()
        for (href in dropped) locals[href]?.let { dropped(it.id) }
        provider.update(
            adapted(ContentUris.withAppendedId(Calendars.CONTENT_URI, shelf.id)),
            ContentValues().apply { put(Calendars.CAL_SYNC2, "${given.getLong("revision")}") },
            null,
            null,
        )
    }

    /** Brings the phone's rows of a series to PONISTRA's, in one batch: the master's row is kept,
     *  so the phone's Calendar app keeps showing it, and its attendees, reminders and occurrences
     *  are written afresh. A master the phone deleted, or whose answer PONISTRA changed, is
     *  written anew, as the provider takes the user's own answer only with a new row. */
    private fun applied(shelf: Shelf, served: JSONObject, found: Local?) {
        val href = served.getString("href")
        val array = served.getJSONArray("parts")
        val parts = (0 until array.length()).map { partOf(array.getJSONObject(it)) }
        val master = parts.first()
        val kept = found?.takeIf { !it.deleted && it.row[Events.SELF_ATTENDEE_STATUS] == "${Series.answer(master)}" }
        val operations = arrayListOf<ContentProviderOperation>()
        val head = mapOf(
            Events._SYNC_ID to href,
            Events.SYNC_DATA1 to "${served.getLong("revision")}",
            Events.DIRTY to 0,
        )
        if (found != null) {
            operations += ContentProviderOperation.newDelete(adapted(Events.CONTENT_URI))
                .withSelection("${Events.ORIGINAL_ID}=?", arrayOf("${found.id}"))
                .build()
        }
        val masterAt = if (kept != null) {
            operations += ContentProviderOperation.newUpdate(adapted(ContentUris.withAppendedId(Events.CONTENT_URI, kept.id)))
                .withColumns(Series.values(master, shelf.owner) + head)
                .build()
            for (uri in listOf(Attendees.CONTENT_URI, Reminders.CONTENT_URI)) {
                operations += ContentProviderOperation.newDelete(adapted(uri))
                    .withSelection("${Attendees.EVENT_ID}=?", arrayOf("${kept.id}"))
                    .build()
            }
            listed(operations, master, kept.id, null)
            null
        } else {
            if (found != null) {
                operations += ContentProviderOperation.newDelete(adapted(ContentUris.withAppendedId(Events.CONTENT_URI, found.id))).build()
            }
            val at = operations.size
            operations += ContentProviderOperation.newInsert(adapted(Events.CONTENT_URI))
                .withColumns(Series.inserted(master, shelf.owner) + head + mapOf(Events.CALENDAR_ID to shelf.id))
                .build()
            listed(operations, master, null, at)
            at
        }
        for (part in parts.drop(1)) {
            val at = operations.size
            operations += ContentProviderOperation.newInsert(adapted(Events.CONTENT_URI))
                .withColumns(Series.inserted(part, shelf.owner) + mapOf(Events.CALENDAR_ID to shelf.id, Events.ORIGINAL_SYNC_ID to href, Events.DIRTY to 0))
                .apply { if (masterAt == null) withValue(Events.ORIGINAL_ID, kept!!.id) else withValueBackReference(Events.ORIGINAL_ID, masterAt) }
                .build()
            listed(operations, part, null, at)
        }
        provider.applyBatch(operations)
    }

    /** The part's attendees and reminders, for the event with the id or the one the operation at
     *  the index inserts. */
    private fun listed(operations: ArrayList<ContentProviderOperation>, part: Part, id: Long?, at: Int?) {
        fun inserted(uri: Uri, values: Map<String, Any?>) {
            operations += ContentProviderOperation.newInsert(adapted(uri))
                .withColumns(values)
                .apply { if (id != null) withValue(Attendees.EVENT_ID, id) else withValueBackReference(Attendees.EVENT_ID, at!!) }
                .build()
        }
        part.attendees.forEach { inserted(Attendees.CONTENT_URI, Series.attendee(it)) }
        part.reminders.forEach {
            inserted(Reminders.CONTENT_URI, mapOf(Reminders.MINUTES to it, Reminders.METHOD to Reminders.METHOD_ALERT))
        }
    }

    private fun attendees(id: Long): List<Attendee> {
        val found = mutableListOf<Attendee>()
        val columns = arrayOf(Attendees.ATTENDEE_EMAIL, Attendees.ATTENDEE_NAME, Attendees.ATTENDEE_STATUS, Attendees.ATTENDEE_TYPE)
        provider.query(adapted(Attendees.CONTENT_URI), columns, "${Attendees.EVENT_ID}=?", arrayOf("$id"), null)?.use { rows ->
            while (rows.moveToNext()) {
                val attendee = Series.attendeeOf(columns.withIndex().associate { (at, column) -> column to rows.getString(at) })
                if (attendee.email.isNotEmpty()) found += attendee
            }
        }
        return found
    }

    private fun reminders(id: Long): List<Int> {
        val found = mutableListOf<Int>()
        provider.query(
            adapted(Reminders.CONTENT_URI),
            arrayOf(Reminders.MINUTES, Reminders.METHOD),
            "${Reminders.EVENT_ID}=?",
            arrayOf("$id"),
            null,
        )?.use { rows ->
            while (rows.moveToNext()) {
                if (rows.getInt(1) != Reminders.METHOD_EMAIL) found += rows.getInt(0)
            }
        }
        return found
    }

    /** The series goes from the phone: its master and the occurrences changed on their own. */
    private fun dropped(id: Long) {
        provider.applyBatch(
            arrayListOf(
                ContentProviderOperation.newDelete(adapted(Events.CONTENT_URI))
                    .withSelection("${Events.ORIGINAL_ID}=?", arrayOf("$id"))
                    .build(),
                ContentProviderOperation.newDelete(adapted(ContentUris.withAppendedId(Events.CONTENT_URI, id))).build(),
            ),
        )
        result.stats.numDeletes++
    }

    private fun named(id: Long, href: String) {
        provider.applyBatch(
            arrayListOf(
                ContentProviderOperation.newUpdate(adapted(ContentUris.withAppendedId(Events.CONTENT_URI, id)))
                    .withValue(Events._SYNC_ID, href)
                    .build(),
                ContentProviderOperation.newUpdate(adapted(Events.CONTENT_URI))
                    .withSelection("${Events.ORIGINAL_ID}=?", arrayOf("$id"))
                    .withValue(Events.ORIGINAL_SYNC_ID, href)
                    .build(),
            ),
        )
    }

    private fun partOf(json: JSONObject): Part {
        val attendees = json.getJSONArray("attendees")
        return Part(
            recurrenceId = if (json.isNull("recurrence_id")) null else json.getLong("recurrence_id"),
            summary = json.getString("summary"),
            location = json.getString("location"),
            description = json.getString("description"),
            allDay = json.getBoolean("all_day"),
            starts = json.getLong("starts"),
            ends = json.getLong("ends"),
            zone = json.getString("zone"),
            rrule = json.getString("rrule"),
            rdates = longs(json.getJSONArray("rdates")),
            exdates = longs(json.getJSONArray("exdates")),
            status = json.getString("status"),
            busy = json.getBoolean("busy"),
            private = json.getBoolean("private"),
            organizer = json.getJSONObject("organizer").let { if (it.has("email")) it.getString("email") else "" },
            attendees = (0 until attendees.length()).map { at ->
                val attendee = attendees.getJSONObject(at)
                Attendee(attendee.getString("email"), attendee.optString("name"), attendee.optString("status"), attendee.optString("role"))
            },
            reminders = json.getJSONArray("reminders").let { array -> (0 until array.length()).map(array::getInt) },
            response = json.getString("response"),
            dayOff = json.getString("day_off"),
        )
    }

    private fun partJson(part: Part) = JSONObject()
        .put("recurrence_id", part.recurrenceId ?: JSONObject.NULL)
        .put("summary", part.summary)
        .put("location", part.location)
        .put("description", part.description)
        .put("all_day", part.allDay)
        .put("starts", part.starts)
        .put("ends", part.ends)
        .put("zone", part.zone)
        .put("rrule", part.rrule)
        .put("rdates", JSONArray(part.rdates))
        .put("exdates", JSONArray(part.exdates))
        .put("status", part.status)
        .put("busy", part.busy)
        .put("private", part.private)
        .put("attendees", JSONArray(part.attendees.map { JSONObject().put("email", it.email).put("name", it.name) }))
        .put("reminders", JSONArray(part.reminders))
        .put("response", part.response)
        .put("day_off", part.dayOff)

    private fun longs(array: JSONArray) = (0 until array.length()).map(array::getLong)

    private fun ContentProviderOperation.Builder.withColumns(values: Map<String, Any?>) =
        apply { values.forEach { (column, value) -> withValue(column, value) } }

    private fun series(shelf: Shelf, href: String): HttpUrl =
        root.newBuilder().addPathSegment("${shelf.pk}").addPathSegment(href).build()

    private fun call(request: Request.Builder): Response = PhoneSync.call(password, request)

    private fun unexpected(answer: Response) = PhoneSync.unexpected(answer)

    private fun adapted(uri: Uri): Uri = uri.buildUpon()
        .appendQueryParameter(CalendarContract.CALLER_IS_SYNCADAPTER, "true")
        .appendQueryParameter(Calendars.ACCOUNT_NAME, account.name)
        .appendQueryParameter(Calendars.ACCOUNT_TYPE, account.type)
        .build()

    companion object {
        private const val TAG = "Ponistra"
        private val JSON = "application/json".toMediaType()
    }
}
