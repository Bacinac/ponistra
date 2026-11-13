package biz.boskovic.ponistra

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

class InstallationTest {
    @Test
    fun `an address becomes the https origin it names`() {
        assertEquals("https://ponistra.tvrtka.hr", Installation.originOf(" Ponistra.Tvrtka.hr/ "))
        assertEquals("https://ponistra.tvrtka.hr", Installation.originOf("https://ponistra.tvrtka.hr/settings"))
        assertEquals("https://office.example.com:8443", Installation.originOf("office.example.com:8443"))
    }

    @Test
    fun `an address that names no https origin is refused`() {
        listOf("", "  ", "http://ponistra.tvrtka.hr", "https://ime@ponistra.tvrtka.hr", "ponistra tvrtka", "https://")
            .forEach { assertNull(Installation.originOf(it), it) }
    }

    @Test
    fun `a connect link brings the origin and the pairing code`() {
        val link = Installation.linkOf("ponistra://connect?origin=https%3A%2F%2Fponistra.tvrtka.hr&code=12%3A1tC5Xh%3Asig")
        assertEquals("https://ponistra.tvrtka.hr", link?.origin)
        assertEquals("12:1tC5Xh:sig", link?.code)
    }

    @Test
    fun `a link without both or for another app is refused`() {
        listOf(
            "ponistra://connect?origin=https%3A%2F%2Fponistra.tvrtka.hr",
            "ponistra://connect?code=abcd",
            "ponistra://connect?origin=http%3A%2F%2Fponistra.tvrtka.hr&code=abcd",
            "https://connect?origin=https%3A%2F%2Fponistra.tvrtka.hr&code=abcd",
            "ponistra://open?origin=https%3A%2F%2Fponistra.tvrtka.hr&code=abcd",
        ).forEach { assertNull(Installation.linkOf(it), it) }
    }

    @Test
    fun `a path stays within the installation`() {
        assertEquals("/settings/app-passwords", Installation.pathOf("/settings/app-passwords"))
        listOf(null, "", "//evil.example", "@evil.example", "settings").forEach {
            assertEquals("/", Installation.pathOf(it), it)
        }
    }
}
