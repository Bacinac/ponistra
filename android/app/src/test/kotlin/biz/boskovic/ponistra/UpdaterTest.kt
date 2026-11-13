package biz.boskovic.ponistra

import java.io.File
import java.nio.file.Files
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows

class UpdaterTest {
    private val installed = Updater.Apk("biz.boskovic.ponistra", 100, setOf("our key"))
    private val offer = Updater.Offer(101, "abc")

    private fun verified(digest: String = "abc", arrived: Updater.Apk? = Updater.Apk("biz.boskovic.ponistra", 101, setOf("our key"))) =
        Updater.verify(offer, digest, installed) { arrived }

    @Test
    fun `a matching package is accepted`() {
        verified()
    }

    @Test
    fun `whatever does not match is refused`() {
        assertThrows<UpdateRejected> { verified(digest = "abd") }
        assertThrows<UpdateRejected> { verified(arrived = null) }
        assertThrows<UpdateRejected> { verified(arrived = Updater.Apk("other.app", 101, setOf("our key"))) }
        assertThrows<UpdateRejected> { verified(arrived = Updater.Apk("biz.boskovic.ponistra", 102, setOf("our key"))) }
        assertThrows<UpdateRejected> { verified(arrived = Updater.Apk("biz.boskovic.ponistra", 101, setOf("their key"))) }
        assertThrows<UpdateRejected> {
            Updater.verify(offer, "abc", Updater.Apk("biz.boskovic.ponistra", 100, emptySet())) {
                Updater.Apk("biz.boskovic.ponistra", 101, emptySet())
            }
        }
    }

    @Test
    fun `the digest is the file's SHA-256`() {
        val file = File.createTempFile("update", ".apk").apply { deleteOnExit() }
        Files.writeString(file.toPath(), "ponistra")
        assertEquals("d7146218f2e0cb0c6643b2e724c5c4acd98592394a915837db6e1d3a395ed6a7", Updater.sha256(file))
    }
}
