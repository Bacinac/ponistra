package biz.boskovic.ponistra

import android.provider.CalendarContract.Attendees
import android.provider.CalendarContract.Events
import java.time.Instant
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

class SeriesTest {
    private val owner = "ivo@example.com"
    private val kolegij = Part(
        recurrenceId = null,
        summary = "Kolegij",
        location = "Ured",
        description = "Dnevni red u privitku",
        allDay = false,
        starts = at("2026-11-03T08:00:00Z"),
        ends = at("2026-11-03T09:00:00Z"),
        zone = "Europe/Zagreb",
        rrule = "FREQ=WEEKLY;COUNT=10",
        rdates = listOf(at("2026-12-24T08:00:00Z")),
        exdates = listOf(at("2026-11-10T08:00:00Z"), at("2026-11-17T08:00:00Z")),
        status = "tentative",
        busy = false,
        private = true,
        organizer = "ana@example.org",
        attendees = listOf(Attendee("ivo@example.com", "Ivo", "accepted", "required")),
        reminders = listOf(10, 30),
        response = "accepted",
        dayOff = "after",
    )

    private fun at(text: String) = Instant.parse(text).toEpochMilli()

    private fun row(values: Map<String, Any?>) = values.mapValues { it.value?.toString() }

    @Test
    fun `a series comes back from the row it becomes as it was`() {
        val values = Series.inserted(kolegij, owner)
        assertEquals("P3600S", values[Events.DURATION])
        assertNull(values[Events.DTEND])
        assertEquals("20261110T080000Z,20261117T080000Z", values[Events.EXDATE])
        assertEquals(Events.STATUS_TENTATIVE, values[Events.STATUS])
        assertEquals(Attendees.ATTENDEE_STATUS_ACCEPTED, values[Events.SELF_ATTENDEE_STATUS])
        assertEquals(kolegij, Series.part(row(values), kolegij.attendees, kolegij.reminders, owner))
    }

    @Test
    fun `a row that exists is written without what the provider keeps or refuses`() {
        val values = Series.values(kolegij, owner)
        assertFalse(Events.SELF_ATTENDEE_STATUS in values)
        assertFalse(Events.HAS_ALARM in values)
        assertEquals(Series.inserted(kolegij, owner) - Events.SELF_ATTENDEE_STATUS, values)
    }

    @Test
    fun `a single event ends by its end and an occurrence changed on its own by its own`() {
        val single = kolegij.copy(rrule = "", rdates = emptyList(), exdates = emptyList(), dayOff = "")
        val values = Series.inserted(single, owner)
        assertEquals(single.ends, values[Events.DTEND])
        assertNull(values[Events.DURATION])
        val moved = single.copy(recurrenceId = at("2026-11-10T08:00:00Z"), dayOff = Series.MOVED)
        val written = Series.inserted(moved, owner)
        assertEquals(moved.recurrenceId, written[Events.ORIGINAL_INSTANCE_TIME])
        assertEquals(moved, Series.part(row(written), moved.attendees, moved.reminders, owner))
    }

    @Test
    fun `an all-day series lasts whole days in UTC`() {
        val holiday = kolegij.copy(
            allDay = true,
            starts = at("2026-12-21T00:00:00Z"),
            ends = at("2026-12-23T00:00:00Z"),
            zone = "",
            rdates = emptyList(),
            exdates = listOf(at("2026-12-28T00:00:00Z")),
        )
        val values = Series.inserted(holiday, owner)
        assertEquals("P2D", values[Events.DURATION])
        assertEquals("UTC", values[Events.EVENT_TIMEZONE])
        assertEquals("20261228T000000Z", values[Events.EXDATE])
        assertEquals(holiday, Series.part(row(values), holiday.attendees, holiday.reminders, owner))
    }

    @Test
    fun `the user's own meeting names no organizer of its own`() {
        val own = kolegij.copy(organizer = "", attendees = emptyList(), response = "")
        val values = Series.inserted(own, owner)
        assertEquals(owner, values[Events.ORGANIZER])
        assertEquals(own, Series.part(row(values), emptyList(), own.reminders, "IVO@example.com"))
    }

    @Test
    fun `dates are read as a calendar app may have written them`() {
        val written = "Europe/Zagreb;20261110T090000,20261117T090000\n20261124T080000Z\n20261201"
        assertEquals(
            listOf(
                at("2026-11-10T08:00:00Z"),
                at("2026-11-17T08:00:00Z"),
                at("2026-11-24T08:00:00Z"),
                at("2026-12-01T00:00:00Z"),
            ),
            Series.datesOf(written),
        )
        assertEquals(emptyList<Long>(), Series.datesOf(null))
    }

    @Test
    fun `durations are read in every way Android and RFC 5545 write them`() {
        assertEquals(3_600_000L, Series.lasting("P3600S"))
        assertEquals(5_400_000L, Series.lasting("PT1H30M"))
        assertEquals(2 * 86_400_000L, Series.lasting("P2D"))
        assertEquals(7 * 86_400_000L, Series.lasting("P1W"))
        assertNull(Series.lasting("soon"))
    }

    @Test
    fun `an attendee comes back from the row they become`() {
        val attendee = Attendee("ana@example.org", "Ana", "tentative", "optional")
        assertEquals(attendee, Series.attendeeOf(row(Series.attendee(attendee))))
    }
}
