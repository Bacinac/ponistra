package biz.boskovic.ponistra

import android.provider.ContactsContract.CommonDataKinds.Event
import android.provider.ContactsContract.CommonDataKinds.Organization
import android.provider.ContactsContract.CommonDataKinds.Phone
import android.provider.ContactsContract.CommonDataKinds.Relation
import android.provider.ContactsContract.CommonDataKinds.StructuredName
import android.provider.ContactsContract.CommonDataKinds.StructuredPostal
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class CardsTest {
    private val fields = mapOf(
        "name" to "Ana Horvat", "given" to "Ana", "family" to "Horvat", "middle" to "", "prefix" to "dr.",
        "suffix" to "", "nickname" to "", "organisation" to "Firma d.o.o.", "department" to "Nabava",
        "title" to "Voditeljica", "birthday" to "--05-17", "note" to "Zove poslijepodne",
    )
    private val points = listOf(
        Point("phone", "mobile", "+385 91 234 5678"),
        Point("phone", "fax", "+385 1 234 5679"),
        Point("email", "work", "ana@firma.test"),
        Point("email", "Privatno", "ana@example.com"),
        Point("address", "work", "Ilica 1\n10000 Zagreb", listOf("", "", "Ilica 1", "Zagreb", "", "10000", "Hrvatska")),
        Point("url", "", "https://firma.test"),
    )

    @Test
    fun `a contact comes back from the rows it becomes as it was`() {
        val card = Card(fields, points)
        assertEquals(card, Cards.card(Cards.rows(card)))
    }

    @Test
    fun `a label of the user's own is the row's custom label`() {
        val row = Cards.rows(Card(fields, points)).first { it.values.containsValue("ana@example.com") }
        assertEquals("0", row.values["data2"])
        assertEquals("Privatno", row.values["data3"])
    }

    @Test
    fun `a contact of nothing but a firm has no name row`() {
        val rows = Cards.rows(Card(mapOf("organisation" to "Firma d.o.o."), emptyList()))
        assertEquals(listOf(Organization.CONTENT_ITEM_TYPE), rows.map { it.mimetype })
    }

    @Test
    fun `a phone type PONISTRA has no word for takes the nearest`() {
        val rows = listOf(
            Row(Phone.CONTENT_ITEM_TYPE, mapOf("data1" to "091 111", "data2" to "${Phone.TYPE_WORK_MOBILE}")),
            Row(Phone.CONTENT_ITEM_TYPE, mapOf("data1" to "091 222", "data2" to "${Phone.TYPE_CAR}")),
            Row(Phone.CONTENT_ITEM_TYPE, mapOf("data1" to "091 333", "data2" to null)),
        )
        assertEquals(listOf("mobile", "other", ""), Cards.card(rows).points.map { it.label })
    }

    @Test
    fun `rows that are not PONISTRA's stay out of the card`() {
        val rows = listOf(
            Row(StructuredName.CONTENT_ITEM_TYPE, mapOf("data1" to "Ana Horvat", "data2" to "Ana", "data3" to "Horvat")),
            Row(Event.CONTENT_ITEM_TYPE, mapOf("data1" to "2010-06-12", "data2" to "${Event.TYPE_ANNIVERSARY}")),
            Row(Relation.CONTENT_ITEM_TYPE, mapOf("data1" to "Marko Horvat", "data2" to "${Relation.TYPE_SPOUSE}")),
        )
        assertFalse(Cards.owned(Event.CONTENT_ITEM_TYPE, rows[1].values))
        assertFalse(Cards.owned(Relation.CONTENT_ITEM_TYPE, rows[2].values))
        val card = Cards.card(rows)
        assertEquals("", card.fields["birthday"])
        assertTrue(card.points.isEmpty())
    }

    @Test
    fun `a birthday PONISTRA would refuse is left out`() {
        val rows = listOf(Row(Event.CONTENT_ITEM_TYPE, mapOf("data1" to "17.05.1980.", "data2" to "${Event.TYPE_BIRTHDAY}")))
        assertEquals("", Cards.card(rows).fields["birthday"])
    }

    @Test
    fun `an address given as one text keeps it`() {
        val rows = listOf(
            Row(
                StructuredPostal.CONTENT_ITEM_TYPE,
                mapOf("data1" to "Ilica 1, Zagreb", "data2" to "${StructuredPostal.TYPE_HOME}", "data4" to "Ilica 1, Zagreb"),
            ),
        )
        val point = Cards.card(rows).points.single()
        assertEquals("home", point.label)
        assertEquals("Ilica 1, Zagreb", point.parts[2])
    }

    @Test
    fun `a contact of no values is empty`() {
        assertTrue(Cards.empty(Cards.card(emptyList())))
        assertFalse(Cards.empty(Card(emptyMap(), listOf(Point("email", "", "ana@firma.test")))))
    }
}
