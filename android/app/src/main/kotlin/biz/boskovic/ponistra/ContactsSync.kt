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
import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.net.Uri
import android.os.Bundle
import android.os.IBinder
import android.provider.ContactsContract
import android.provider.ContactsContract.CommonDataKinds.GroupMembership
import android.provider.ContactsContract.CommonDataKinds.Photo
import android.provider.ContactsContract.Data
import android.provider.ContactsContract.Groups
import android.provider.ContactsContract.RawContacts
import android.util.Base64
import android.util.Log
import java.io.ByteArrayOutputStream
import java.io.FileNotFoundException
import java.io.IOException
import java.nio.ByteBuffer
import java.util.UUID
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject

/** The user's PONISTRA address book in the phone's own contacts, both ways, through the account the
 *  phone connected with (D26), and beside it the book of each shared mailbox the user reaches, as a
 *  group bearing the mailbox's name. PONISTRA holds the truth: a change the phone made to a contact
 *  that changed there meanwhile gives way to PONISTRA's. */
object ContactsSync : PhoneSync(
    ContactsContract.AUTHORITY,
    arrayOf(Manifest.permission.READ_CONTACTS, Manifest.permission.WRITE_CONTACTS),
    1,
    "contacts",
    R.string.contacts_channel,
    R.string.contacts_refused_title,
    R.string.contacts_refused_text,
)

class ContactsSyncAdapter(context: Context) : AbstractThreadedSyncAdapter(context, false) {
    override fun onPerformSync(
        account: Account,
        extras: Bundle,
        authority: String,
        provider: ContentProviderClient,
        result: SyncResult,
    ) = ContactsSync.performed(context, account, result) { origin, password ->
        PhoneBook(account, AccountManager.get(context), provider, origin, password, result).sync()
    }
}

class ContactsSyncService : Service() {
    private val adapter by lazy { ContactsSyncAdapter(applicationContext) }

    override fun onBind(intent: Intent?): IBinder? = adapter.syncAdapterBinder
}

/** One sync of an account's contacts: what the phone deleted and changed goes up, then what changed
 *  in PONISTRA since the revision the phone read last comes down, book by book: the user's own,
 *  which names the shared mailboxes, then each mailbox's. A contact's href (its name in the address
 *  book) is its SOURCE_ID; SYNC1 holds the revision the phone has of it, SYNC2 the photo PONISTRA
 *  has, SYNC3 which photo row the phone held then, SYNC4 the mailbox whose book it is in (none for
 *  the user's own). A mailbox's group has the mailbox as its SOURCE_ID and SYNC1 set where the
 *  user only reads it, as are its contacts. */
private class PhoneBook(
    private val account: Account,
    private val manager: AccountManager,
    private val provider: ContentProviderClient,
    private val origin: String,
    private val password: String,
    private val result: SyncResult,
) {
    private class Local(
        val id: Long,
        val href: String?,
        val revision: Long?,
        val photo: String?,
        val held: String?,
        val dirty: Boolean,
        val deleted: Boolean,
        val starred: Boolean,
        val box: String,
    )

    /** A mailbox's book as the phone holds it: its group, and whether the user only reads it. */
    private class Shelf(val box: String, val group: Long?, val readOnly: Boolean)

    private val book: HttpUrl = "$origin/api/device/contacts".toHttpUrl()
    private val own = Shelf(OWN, null, false)

    fun sync() {
        visible()
        val locals = locals()
        val shelves = shelves()
        val whole = mutableSetOf<String>()
        for (local in locals.filter { it.deleted }) if (removed(local)) whole += local.box
        for (local in locals.filter { it.dirty && !it.deleted }) {
            val placed = placed(local, shelves)
            if (changed(local, placed)) whole += placed
        }
        val mailboxes = read(own, OWN in whole)
        val listed = mutableSetOf<String>()
        for (at in 0 until mailboxes.length()) {
            val mailbox = mailboxes.getJSONObject(at)
            val box = "${mailbox.getLong("id")}"
            val readOnly = mailbox.getBoolean("read_only")
            listed += box
            // A role that changed changes every contact of the book, which no revision tells.
            val changedRole = shelves[box]?.readOnly != readOnly
            read(shelved(box, mailbox.getString("name"), readOnly, shelves[box]), box in whole || changedRole)
        }
        for ((box, shelf) in shelves) if (box !in listed) forgotten(shelf)
        manager.setUserData(account, SHAPE_READ, "$SHAPE")
    }

    /** The mailboxes' groups as the phone holds them, by mailbox. */
    private fun shelves(): Map<String, Shelf> {
        val found = mutableMapOf<String, Shelf>()
        provider.query(
            adapted(Groups.CONTENT_URI),
            arrayOf(Groups._ID, Groups.SOURCE_ID, Groups.SYNC1),
            "${Groups.ACCOUNT_NAME}=? AND ${Groups.ACCOUNT_TYPE}=? AND ${Groups.DELETED}=0",
            arrayOf(account.name, account.type),
            null,
        )?.use { rows ->
            while (rows.moveToNext()) {
                val box = rows.getString(1) ?: continue
                found[box] = Shelf(box, rows.getLong(0), rows.getString(2) == READ_ONLY)
            }
        }
        return found
    }

    /** The mailbox's group as PONISTRA names it, made where the phone has none. */
    private fun shelved(box: String, name: String, readOnly: Boolean, held: Shelf?): Shelf {
        val values = ContentValues().apply {
            put(Groups.TITLE, name)
            put(Groups.SYNC1, if (readOnly) READ_ONLY else null)
            put(Groups.GROUP_VISIBLE, 1)
            put(Groups.GROUP_IS_READ_ONLY, 1)
        }
        if (held != null) {
            provider.update(adapted(ContentUris.withAppendedId(Groups.CONTENT_URI, held.group!!)), values, null, null)
            return Shelf(box, held.group, readOnly)
        }
        values.put(Groups.ACCOUNT_NAME, account.name)
        values.put(Groups.ACCOUNT_TYPE, account.type)
        values.put(Groups.SOURCE_ID, box)
        return Shelf(box, ContentUris.parseId(provider.insert(adapted(Groups.CONTENT_URI), values)!!), readOnly)
    }

    /** Takes off the phone the book of a mailbox the user no longer reaches. */
    private fun forgotten(shelf: Shelf) {
        result.stats.numDeletes += provider.delete(
            adapted(RawContacts.CONTENT_URI),
            "${RawContacts.ACCOUNT_NAME}=? AND ${RawContacts.ACCOUNT_TYPE}=? AND ${RawContacts.SYNC4}=?",
            arrayOf(account.name, account.type, shelf.box),
        ).toLong()
        provider.delete(adapted(ContentUris.withAppendedId(Groups.CONTENT_URI, shelf.group!!)), null, null)
        manager.setUserData(account, since(shelf.box), null)
    }

    /** The book a contact the phone changed goes to: the one it came from, or for one made on the
     *  phone the first mailbox the user writes whose group it was put in, else the user's own. */
    private fun placed(local: Local, shelves: Map<String, Shelf>): String {
        if (local.href != null) return local.box
        val writable = shelves.values.filter { !it.readOnly }.associateBy { "${it.group}" }
        provider.query(
            adapted(Data.CONTENT_URI),
            arrayOf(GroupMembership.GROUP_ROW_ID),
            "${Data.RAW_CONTACT_ID}=? AND ${Data.MIMETYPE}=?",
            arrayOf("${local.id}", GroupMembership.CONTENT_ITEM_TYPE),
            null,
        )?.use { rows ->
            while (rows.moveToNext()) writable[rows.getString(0)]?.let { return it.box }
        }
        return OWN
    }

    /** Contacts of an account in no group are hidden from the contacts app unless it says so. */
    private fun visible() {
        provider.insert(
            adapted(ContactsContract.Settings.CONTENT_URI),
            ContentValues().apply {
                put(ContactsContract.Settings.ACCOUNT_NAME, account.name)
                put(ContactsContract.Settings.ACCOUNT_TYPE, account.type)
                put(ContactsContract.Settings.UNGROUPED_VISIBLE, 1)
                put(ContactsContract.Settings.SHOULD_SYNC, 1)
            },
        )
    }

    private fun locals(): List<Local> {
        val found = mutableListOf<Local>()
        provider.query(
            adapted(RawContacts.CONTENT_URI),
            arrayOf(
                RawContacts._ID, RawContacts.SOURCE_ID, RawContacts.SYNC1, RawContacts.SYNC2, RawContacts.SYNC3,
                RawContacts.DIRTY, RawContacts.DELETED, RawContacts.STARRED, RawContacts.SYNC4,
            ),
            null,
            null,
            null,
        )?.use { rows ->
            while (rows.moveToNext()) {
                found += Local(
                    rows.getLong(0),
                    rows.getString(1),
                    rows.getString(2)?.toLongOrNull(),
                    rows.getString(3),
                    rows.getString(4),
                    rows.getInt(5) != 0,
                    rows.getInt(6) != 0,
                    rows.getInt(7) != 0,
                    rows.getString(8) ?: OWN,
                )
            }
        }
        return found
    }

    /** Deletes in PONISTRA a contact the phone deleted; whether PONISTRA changed it meanwhile or
     *  keeps it from the user, so the whole book must be read again to bring it back. */
    private fun removed(local: Local): Boolean {
        var whole = false
        if (local.href != null && local.revision != null) {
            val url = card(local.box, local.href).newBuilder().addQueryParameter("revision", "${local.revision}").build()
            call(Request.Builder().url(url).delete()).use { answer ->
                if (answer.code !in setOf(204, 403, 404, 412)) throw unexpected(answer)
                whole = answer.code in setOf(403, 412)
            }
        }
        dropped(local.id)
        return whole
    }

    /** Sends a contact the phone changed to the mailbox's book `box`; whether PONISTRA changed it
     *  meanwhile or keeps it from the user, so the whole book must be read again to take PONISTRA's. */
    private fun changed(local: Local, box: String): Boolean {
        val card = Cards.card(rows(local.id))
        if (Cards.empty(card)) return false
        val href = local.href ?: "${UUID.randomUUID()}.vcf".also { named(local.id, it, box) }
        val held = held(local.id)
        val pictured = held != local.held.orEmpty()
        val sent = JSONObject()
            .put("fields", JSONObject(card.fields))
            .put("points", JSONArray(card.points.map(::pointJson)))
            .put("revision", local.revision ?: JSONObject.NULL)
            .put("starred", local.starred)
        if (pictured) sent.put("photo", photo(local.id)?.let { Base64.encodeToString(it, Base64.NO_WRAP) } ?: JSONObject.NULL)
        call(Request.Builder().url(card(box, href)).put(sent.toString().toRequestBody(JSON))).use { answer ->
            when (answer.code) {
                200, 201 -> {
                    val served = JSONObject(answer.body.string())
                    apply(local.id, served, if (pictured) served.text("photo") else local.photo, null)
                    result.stats.numUpdates++
                }
                403, 412 -> return true
                404 -> dropped(local.id)
                400 -> {
                    Log.w(TAG, "$origin refused the contact $href: ${answer.body.string()}")
                    result.stats.numParseExceptions++
                }
                else -> throw unexpected(answer)
            }
        }
        return false
    }

    /** Reads the book what changed since the phone read it last, or whole; the mailboxes the user's
     *  own names. */
    private fun read(shelf: Shelf, whole: Boolean): JSONArray {
        val read = manager.getUserData(account, SHAPE_READ) == "$SHAPE"
        val since = if (whole || !read) 0 else manager.getUserData(account, since(shelf.box))?.toLongOrNull() ?: 0
        return read(shelf, since)
    }

    private fun read(shelf: Shelf, since: Long): JSONArray {
        val url = boxed(book, shelf.box).newBuilder().addQueryParameter("since", "$since").build()
        val given = call(Request.Builder().url(url).get()).use { answer ->
            if (answer.code == 410 && since > 0) return read(shelf, 0)
            if (!answer.isSuccessful) throw unexpected(answer)
            JSONObject(answer.body.string())
        }
        val locals = locals().filter { it.href != null && it.box == shelf.box }.associateBy { it.href!! }
        val contacts = given.getJSONArray("contacts")
        val listed = mutableSetOf<String>()
        for (at in 0 until contacts.length()) {
            val served = contacts.getJSONObject(at)
            val href = served.getString("href")
            listed += href
            val local = locals[href]
            if (local == null) {
                made(served, shelf)
                result.stats.numInserts++
            } else {
                if (local.starred && !served.getBoolean("starred")) unstarred(local.id)
                apply(local.id, served, local.photo, shelf)
                result.stats.numUpdates++
            }
        }
        val gone = given.getJSONArray("gone").let { array -> (0 until array.length()).map(array::getString) }
        val dropped = if (since == 0L) locals.keys - listed else gone.toSet()
        for (href in dropped) locals[href]?.let { dropped(it.id) }
        manager.setUserData(account, since(shelf.box), "${given.getLong("revision")}")
        return given.optJSONArray("mailboxes") ?: JSONArray()
    }

    private fun made(served: JSONObject, shelf: Shelf) {
        val operations = arrayListOf(
            ContentProviderOperation.newInsert(adapted(RawContacts.CONTENT_URI))
                .withValue(RawContacts.ACCOUNT_NAME, account.name)
                .withValue(RawContacts.ACCOUNT_TYPE, account.type)
                .withValue(RawContacts.SOURCE_ID, served.getString("href"))
                .withValue(RawContacts.SYNC1, "${served.getLong("revision")}")
                .withValue(RawContacts.SYNC4, shelf.box.ifEmpty { null })
                .withValue(RawContacts.RAW_CONTACT_IS_READ_ONLY, if (shelf.readOnly) 1 else 0)
                .withValue(RawContacts.STARRED, starred(served))
                .build(),
        )
        shelf.group?.let { group ->
            operations += ContentProviderOperation.newInsert(adapted(Data.CONTENT_URI))
                .withValueBackReference(Data.RAW_CONTACT_ID, 0)
                .withValue(Data.MIMETYPE, GroupMembership.CONTENT_ITEM_TYPE)
                .withValue(GroupMembership.GROUP_ROW_ID, group)
                .build()
        }
        for (row in Cards.rows(cardOf(served))) {
            operations += ContentProviderOperation.newInsert(adapted(Data.CONTENT_URI))
                .withValueBackReference(Data.RAW_CONTACT_ID, 0)
                .withValue(Data.MIMETYPE, row.mimetype)
                .apply { row.values.forEach { (column, value) -> withValue(column, value) } }
                .build()
        }
        val id = ContentUris.parseId(provider.applyBatch(operations)[0].uri!!)
        pictured(id, served, null)
    }

    /** Takes the star off the person, as the contacts app does: Android stars every account's card
     *  of them together and shows the person starred while any card is, so a star taken off this
     *  account's card alone would stay. Not as the sync adapter, so the other accounts carry it up;
     *  before `apply`, which clears the change it marks on this account's card. */
    private fun unstarred(id: Long) {
        val person = provider.query(
            adapted(ContentUris.withAppendedId(RawContacts.CONTENT_URI, id)),
            arrayOf(RawContacts.CONTACT_ID),
            null,
            null,
            null,
        )?.use { rows -> if (rows.moveToFirst()) rows.getLong(0) else null } ?: return
        val values = ContentValues().apply { put(ContactsContract.Contacts.STARRED, 0) }
        provider.update(ContentUris.withAppendedId(ContactsContract.Contacts.CONTENT_URI, person), values, null, null)
    }

    /** Brings the phone's rows of a contact to PONISTRA's: rows that stayed the same are kept, so
     *  the number the user made the default stays so. `photo` is the photo PONISTRA has as the
     *  phone knows it, which is fetched only when it differs; `shelf`, where given, the book whose
     *  read only the contact becomes. */
    private fun apply(id: Long, served: JSONObject, photo: String?, shelf: Shelf?) {
        val wanted = Cards.rows(cardOf(served)).toMutableList()
        val operations = arrayListOf<ContentProviderOperation>()
        for ((row, values) in owned(id)) {
            val same = wanted.indexOfFirst { want ->
                want.mimetype == values.mimetype &&
                    want.values.all { (column, value) -> value.orEmpty() == values.values[column].orEmpty() }
            }
            if (same >= 0) {
                wanted.removeAt(same)
            } else {
                operations += ContentProviderOperation.newDelete(adapted(ContentUris.withAppendedId(Data.CONTENT_URI, row))).build()
            }
        }
        for (row in wanted) {
            operations += ContentProviderOperation.newInsert(adapted(Data.CONTENT_URI))
                .withValue(Data.RAW_CONTACT_ID, id)
                .withValue(Data.MIMETYPE, row.mimetype)
                .apply { row.values.forEach { (column, value) -> withValue(column, value) } }
                .build()
        }
        operations += ContentProviderOperation.newUpdate(adapted(ContentUris.withAppendedId(RawContacts.CONTENT_URI, id)))
            .withValue(RawContacts.SOURCE_ID, served.getString("href"))
            .withValue(RawContacts.SYNC1, "${served.getLong("revision")}")
            .withValue(RawContacts.STARRED, starred(served))
            .withValue(RawContacts.DIRTY, 0)
            .apply { shelf?.let { withValue(RawContacts.RAW_CONTACT_IS_READ_ONLY, if (it.readOnly) 1 else 0) } }
            .build()
        provider.applyBatch(operations)
        pictured(id, served, photo)
    }

    /** Gives the contact PONISTRA's photo where it differs from the one the phone has, and notes
     *  which photo row the phone now holds. */
    private fun pictured(id: Long, served: JSONObject, known: String?) {
        val photo = served.text("photo")
        if (photo != known) {
            val operations = arrayListOf(
                ContentProviderOperation.newDelete(adapted(Data.CONTENT_URI))
                    .withSelection("${Data.RAW_CONTACT_ID}=? AND ${Data.MIMETYPE}=?", arrayOf("$id", Photo.CONTENT_ITEM_TYPE))
                    .build(),
            )
            if (photo != null) {
                val bytes = fetched(served.getLong("id")) ?: return
                operations += ContentProviderOperation.newInsert(adapted(Data.CONTENT_URI))
                    .withValue(Data.RAW_CONTACT_ID, id)
                    .withValue(Data.MIMETYPE, Photo.CONTENT_ITEM_TYPE)
                    .withValue(Photo.PHOTO, bytes)
                    .build()
            }
            provider.applyBatch(operations)
        }
        provider.update(
            adapted(ContentUris.withAppendedId(RawContacts.CONTENT_URI, id)),
            ContentValues().apply {
                put(RawContacts.SYNC2, photo)
                put(RawContacts.SYNC3, held(id))
            },
            null,
            null,
        )
    }

    /** PONISTRA's photo of the contact drawn no larger than the phone keeps one, as JPEG; null where
     *  it is no picture the phone can draw. */
    private fun fetched(pk: Long): ByteArray? {
        val url = "$origin/api/contacts/$pk/photo".toHttpUrl()
        val bytes = call(Request.Builder().url(url).get()).use { answer ->
            if (answer.code == 404) return null
            if (!answer.isSuccessful) throw unexpected(answer)
            answer.body.bytes()
        }
        val drawn = try {
            ImageDecoder.decodeBitmap(ImageDecoder.createSource(ByteBuffer.wrap(bytes))) { decoder, info, _ ->
                decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                val side = maxOf(info.size.width, info.size.height)
                if (side > LARGEST) {
                    decoder.setTargetSize(info.size.width * LARGEST / side, info.size.height * LARGEST / side)
                }
            }
        } catch (failure: IOException) {
            PhoneSync.failed("the photo of contact $pk is no picture the phone draws", failure)
            return null
        }
        return ByteArrayOutputStream().use { out ->
            drawn.compress(Bitmap.CompressFormat.JPEG, QUALITY, out)
            out.toByteArray()
        }
    }

    /** Which photo row the contact holds, which changes when the user gives it another; empty for
     *  none. */
    private fun held(id: Long): String {
        provider.query(
            adapted(Data.CONTENT_URI),
            arrayOf(Data._ID, Data.DATA_VERSION, Photo.PHOTO_FILE_ID, Photo.PHOTO),
            "${Data.RAW_CONTACT_ID}=? AND ${Data.MIMETYPE}=?",
            arrayOf("$id", Photo.CONTENT_ITEM_TYPE),
            null,
        )?.use { rows ->
            while (rows.moveToNext()) {
                if (!rows.isNull(2) || !rows.isNull(3)) return "${rows.getLong(0)}:${rows.getLong(1)}"
            }
        }
        return ""
    }

    /** The contact's photo as the phone holds it at its largest; null for none. */
    private fun photo(id: Long): ByteArray? {
        val raw = ContentUris.withAppendedId(RawContacts.CONTENT_URI, id)
        try {
            provider.openAssetFile(Uri.withAppendedPath(raw, RawContacts.DisplayPhoto.CONTENT_DIRECTORY), "r")
                ?.use { return it.createInputStream().readBytes() }
        } catch (_: FileNotFoundException) {
            // A photo kept only as its thumbnail has no display photo.
        }
        provider.query(
            adapted(Data.CONTENT_URI),
            arrayOf(Photo.PHOTO),
            "${Data.RAW_CONTACT_ID}=? AND ${Data.MIMETYPE}=?",
            arrayOf("$id", Photo.CONTENT_ITEM_TYPE),
            null,
        )?.use { rows -> if (rows.moveToFirst() && !rows.isNull(0)) return rows.getBlob(0) }
        return null
    }

    private fun dropped(id: Long) {
        provider.delete(adapted(ContentUris.withAppendedId(RawContacts.CONTENT_URI, id)), null, null)
        result.stats.numDeletes++
    }

    private fun named(id: Long, href: String, box: String) {
        provider.update(
            adapted(ContentUris.withAppendedId(RawContacts.CONTENT_URI, id)),
            ContentValues().apply {
                put(RawContacts.SOURCE_ID, href)
                put(RawContacts.SYNC4, box.ifEmpty { null })
            },
            null,
            null,
        )
    }

    private fun rows(id: Long): List<Row> = owned(id).map { it.second }

    /** The contact's rows that are PONISTRA's, by their ids. */
    private fun owned(id: Long): List<Pair<Long, Row>> {
        val found = mutableListOf<Pair<Long, Row>>()
        provider.query(
            adapted(Data.CONTENT_URI),
            arrayOf(Data._ID, Data.MIMETYPE) + COLUMNS,
            "${Data.RAW_CONTACT_ID}=?",
            arrayOf("$id"),
            null,
        )?.use { rows ->
            while (rows.moveToNext()) {
                val mimetype = rows.getString(1) ?: continue
                val values = COLUMNS.withIndex().associate { (at, column) -> column to rows.getString(at + 2) }
                if (Cards.owned(mimetype, values)) found += rows.getLong(0) to Row(mimetype, values)
            }
        }
        return found
    }

    private fun cardOf(served: JSONObject): Card {
        val fields = served.getJSONObject("fields")
        val points = served.getJSONArray("points")
        return Card(
            fields.keys().asSequence().associateWith { fields.getString(it) },
            (0 until points.length()).map { at ->
                val point = points.getJSONObject(at)
                val parts = point.optJSONArray("parts") ?: JSONArray()
                Point(
                    point.getString("kind"),
                    point.optString("label"),
                    point.getString("value"),
                    (0 until parts.length()).map(parts::getString),
                )
            },
        )
    }

    private fun starred(served: JSONObject): Int = if (served.getBoolean("starred")) 1 else 0

    private fun pointJson(point: Point) = JSONObject()
        .put("kind", point.kind)
        .put("label", point.label)
        .put("value", point.value)
        .put("parts", JSONArray(point.parts))

    // org.json's optString gives JSON's null as the text "null".
    private fun JSONObject.text(key: String): String? = if (isNull(key)) null else getString(key)

    private fun card(box: String, href: String): HttpUrl = boxed(book.newBuilder().addPathSegment(href).build(), box)

    private fun boxed(url: HttpUrl, box: String): HttpUrl =
        if (box == OWN) url else url.newBuilder().addQueryParameter("box", box).build()

    private fun since(box: String) = if (box == OWN) SINCE else "$SINCE-$box"

    private fun call(request: Request.Builder): Response = PhoneSync.call(password, request)

    private fun unexpected(answer: Response) = PhoneSync.unexpected(answer)

    private fun adapted(uri: Uri): Uri = uri.buildUpon()
        .appendQueryParameter(ContactsContract.CALLER_IS_SYNCADAPTER, "true")
        .appendQueryParameter(RawContacts.ACCOUNT_NAME, account.name)
        .appendQueryParameter(RawContacts.ACCOUNT_TYPE, account.type)
        .build()

    companion object {
        private const val TAG = "Ponistra"
        private const val SINCE = "contacts_revision"
        // What the phone takes of a contact; a phone that read the book when it took less, before
        // the favourite, reads it whole once, as the contacts it read then do not come again.
        private const val SHAPE = 2
        private const val SHAPE_READ = "contacts_shape"
        private const val OWN = ""
        private const val READ_ONLY = "read"
        // The side of the display photo the contacts provider keeps, which it shrinks a larger one to.
        private const val LARGEST = 720
        private const val QUALITY = 90
        private val JSON = "application/json".toMediaType()
        private val COLUMNS = (1..14).map { "data$it" }.toTypedArray()
    }
}
