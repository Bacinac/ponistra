package biz.boskovic.ponistra

import android.provider.ContactsContract.CommonDataKinds.BaseTypes
import android.provider.ContactsContract.CommonDataKinds.Email
import android.provider.ContactsContract.CommonDataKinds.Event
import android.provider.ContactsContract.CommonDataKinds.Nickname
import android.provider.ContactsContract.CommonDataKinds.Note
import android.provider.ContactsContract.CommonDataKinds.Organization
import android.provider.ContactsContract.CommonDataKinds.Phone
import android.provider.ContactsContract.CommonDataKinds.StructuredName
import android.provider.ContactsContract.CommonDataKinds.StructuredPostal
import android.provider.ContactsContract.CommonDataKinds.Website
import android.provider.ContactsContract.Data

/** A way to reach a contact as PONISTRA keeps it: kind email, phone, address or url; label work,
 *  home, mobile, fax, pager, main, other or a label of the user's own; a postal address also by
 *  its parts: box, extended, street, city, region, code, country. */
data class Point(val kind: String, val label: String, val value: String, val parts: List<String> = emptyList())

data class Card(val fields: Map<String, String>, val points: List<Point>)

/** A row of the phone's contacts provider: its mimetype and the columns PONISTRA fills, every value
 *  as text, which is how the provider keeps them. */
data class Row(val mimetype: String, val values: Map<String, String?>)

/** A contact of PONISTRA as rows of the phone's contacts provider and back (D26). Only the rows
 *  PONISTRA knows are its own: the rest (messengers, relations, other dates, groups, the photo)
 *  stay on the phone as they are. */
object Cards {
    private val FIELDS = listOf(
        "name", "given", "family", "middle", "prefix", "suffix", "nickname", "organisation", "department", "title",
        "birthday", "note",
    )
    private val NAMES = listOf(
        "name" to StructuredName.DISPLAY_NAME,
        "prefix" to StructuredName.PREFIX,
        "given" to StructuredName.GIVEN_NAME,
        "middle" to StructuredName.MIDDLE_NAME,
        "family" to StructuredName.FAMILY_NAME,
        "suffix" to StructuredName.SUFFIX,
    )
    private val FIRM = listOf(
        "organisation" to Organization.COMPANY,
        "department" to Organization.DEPARTMENT,
        "title" to Organization.TITLE,
    )
    private val PARTS = listOf(
        StructuredPostal.POBOX,
        StructuredPostal.NEIGHBORHOOD,
        StructuredPostal.STREET,
        StructuredPostal.CITY,
        StructuredPostal.REGION,
        StructuredPostal.POSTCODE,
        StructuredPostal.COUNTRY,
    )
    private val BIRTHDAY = Regex("""(\d{4}|-)-\d{2}-\d{2}""")
    private const val LABEL = 100

    private val PHONES = mapOf(
        "mobile" to Phone.TYPE_MOBILE,
        "work" to Phone.TYPE_WORK,
        "home" to Phone.TYPE_HOME,
        "fax" to Phone.TYPE_FAX_WORK,
        "pager" to Phone.TYPE_PAGER,
        "main" to Phone.TYPE_MAIN,
        "other" to Phone.TYPE_OTHER,
        "" to Phone.TYPE_OTHER,
    )
    private val PHONE_LABELS = mapOf(
        Phone.TYPE_MOBILE to "mobile",
        Phone.TYPE_WORK to "work",
        Phone.TYPE_HOME to "home",
        Phone.TYPE_FAX_WORK to "fax",
        Phone.TYPE_FAX_HOME to "fax",
        Phone.TYPE_OTHER_FAX to "fax",
        Phone.TYPE_PAGER to "pager",
        Phone.TYPE_WORK_PAGER to "pager",
        Phone.TYPE_MAIN to "main",
        Phone.TYPE_COMPANY_MAIN to "main",
        Phone.TYPE_WORK_MOBILE to "mobile",
    )
    private val EMAILS = mapOf(
        "work" to Email.TYPE_WORK,
        "home" to Email.TYPE_HOME,
        "mobile" to Email.TYPE_MOBILE,
        "other" to Email.TYPE_OTHER,
        "" to Email.TYPE_OTHER,
    )
    private val ADDRESSES = mapOf(
        "work" to StructuredPostal.TYPE_WORK,
        "home" to StructuredPostal.TYPE_HOME,
        "other" to StructuredPostal.TYPE_OTHER,
        "" to StructuredPostal.TYPE_OTHER,
    )
    private val WEBSITES = mapOf(
        "work" to Website.TYPE_WORK,
        "home" to Website.TYPE_HOME,
        "other" to Website.TYPE_OTHER,
        "" to Website.TYPE_HOMEPAGE,
    )
    private val KINDS = mapOf(
        "phone" to Triple(Phone.CONTENT_ITEM_TYPE, Phone.NUMBER, PHONES),
        "email" to Triple(Email.CONTENT_ITEM_TYPE, Email.ADDRESS, EMAILS),
        "address" to Triple(StructuredPostal.CONTENT_ITEM_TYPE, StructuredPostal.FORMATTED_ADDRESS, ADDRESSES),
        "url" to Triple(Website.CONTENT_ITEM_TYPE, Website.URL, WEBSITES),
    )

    /** Whether the row is one of PONISTRA's: an event only as a birthday. */
    fun owned(mimetype: String, values: Map<String, String?>): Boolean = when (mimetype) {
        Event.CONTENT_ITEM_TYPE -> values[Event.TYPE] == Event.TYPE_BIRTHDAY.toString()
        StructuredName.CONTENT_ITEM_TYPE, Nickname.CONTENT_ITEM_TYPE, Organization.CONTENT_ITEM_TYPE,
        Note.CONTENT_ITEM_TYPE, Phone.CONTENT_ITEM_TYPE, Email.CONTENT_ITEM_TYPE,
        StructuredPostal.CONTENT_ITEM_TYPE, Website.CONTENT_ITEM_TYPE -> true
        else -> false
    }

    fun rows(card: Card): List<Row> {
        val field = { name: String -> card.fields[name].orEmpty().ifEmpty { null } }
        val rows = mutableListOf<Row>()
        if (NAMES.any { (name, _) -> field(name) != null }) {
            rows += Row(StructuredName.CONTENT_ITEM_TYPE, NAMES.associate { (name, column) -> column to field(name) })
        }
        field("nickname")?.let {
            rows += Row(Nickname.CONTENT_ITEM_TYPE, mapOf(Nickname.NAME to it, Nickname.TYPE to "${Nickname.TYPE_DEFAULT}"))
        }
        if (FIRM.any { (name, _) -> field(name) != null }) {
            rows += Row(
                Organization.CONTENT_ITEM_TYPE,
                FIRM.associate { (name, column) -> column to field(name) } +
                    (Organization.TYPE to "${Organization.TYPE_WORK}"),
            )
        }
        field("birthday")?.let {
            rows += Row(Event.CONTENT_ITEM_TYPE, mapOf(Event.START_DATE to it, Event.TYPE to "${Event.TYPE_BIRTHDAY}"))
        }
        field("note")?.let { rows += Row(Note.CONTENT_ITEM_TYPE, mapOf(Note.NOTE to it)) }
        for (point in card.points) {
            val (mimetype, column, types) = KINDS[point.kind] ?: continue
            val type = types[point.label]
            val values = mutableMapOf(
                column to point.value,
                Data.DATA2 to "${type ?: BaseTypes.TYPE_CUSTOM}",
                Data.DATA3 to if (type == null) point.label else null,
            )
            if (point.kind == "address") {
                PARTS.forEachIndexed { at, part -> values[part] = point.parts.getOrNull(at)?.ifEmpty { null } }
            }
            rows += Row(mimetype, values)
        }
        return rows
    }

    /** The card the phone's rows make, of those that are PONISTRA's; a value the server would refuse
     *  is left out. */
    fun card(rows: List<Row>): Card {
        val fields = FIELDS.associateWith { "" }.toMutableMap()
        fun first(mimetype: String) = rows.firstOrNull { it.mimetype == mimetype }?.values
        first(StructuredName.CONTENT_ITEM_TYPE)?.let { name ->
            NAMES.forEach { (field, column) -> fields[field] = name[column].orEmpty().trim() }
        }
        first(Nickname.CONTENT_ITEM_TYPE)?.let { fields["nickname"] = it[Nickname.NAME].orEmpty().trim() }
        first(Organization.CONTENT_ITEM_TYPE)?.let { firm ->
            FIRM.forEach { (field, column) -> fields[field] = firm[column].orEmpty().trim() }
        }
        rows.firstOrNull { it.mimetype == Event.CONTENT_ITEM_TYPE && owned(it.mimetype, it.values) }
            ?.values?.get(Event.START_DATE)?.trim()?.takeIf(BIRTHDAY::matches)?.let { fields["birthday"] = it }
        first(Note.CONTENT_ITEM_TYPE)?.let { fields["note"] = it[Note.NOTE].orEmpty().trim() }
        val points = rows.mapNotNull { row ->
            val (kind, found) = KINDS.entries.firstOrNull { it.value.first == row.mimetype } ?: return@mapNotNull null
            val (_, column, types) = found
            val type = row.values[Data.DATA2]?.toIntOrNull()
            val label = when {
                type == null -> ""
                type == BaseTypes.TYPE_CUSTOM -> row.values[Data.DATA3].orEmpty().trim().take(LABEL)
                kind == "phone" -> PHONE_LABELS[type] ?: "other"
                else -> types.entries.firstOrNull { it.value == type }?.key ?: "other"
            }
            val parts = if (kind == "address") PARTS.map { row.values[it].orEmpty().trim() } else emptyList()
            val value = row.values[column].orEmpty().trim()
            Point(kind, label, value, parts).takeIf { value.isNotEmpty() || parts.any(String::isNotEmpty) }
        }
        return Card(fields, points)
    }

    /** Whether the rows hold nothing the server would keep. */
    fun empty(card: Card): Boolean = card.fields.values.all(String::isEmpty) && card.points.isEmpty()
}
