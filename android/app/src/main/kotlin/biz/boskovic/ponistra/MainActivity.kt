package biz.boskovic.ponistra

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.util.Log
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.browser.trusted.sharing.ShareData
import androidx.core.net.toUri
import com.google.androidbrowserhelper.trusted.LauncherActivity
import com.google.androidbrowserhelper.trusted.LauncherActivityMetadata
import com.google.androidbrowserhelper.trusted.SessionStore
import com.google.androidbrowserhelper.trusted.SharingUtils
import com.google.androidbrowserhelper.trusted.TwaLauncher
import java.io.IOException
import kotlin.concurrent.thread

/** Opens the installation's web app in Chrome as the app itself (a Trusted Web Activity), once the
 *  phone knows its address. */
class MainActivity : LauncherActivity() {
    override fun shouldLaunchImmediately(): Boolean {
        UpdateWorker.schedule(this)
        PhoneSync.all.filter { it.granted(this) }.forEach { it.request(this) }
        val origin = Installation.current(this)
        if (origin == null || intent.action == CHANGE) {
            ask(origin)
            return false
        }
        val missing = PhoneSync.adopted(this)
        if (missing.isNotEmpty()) {
            requestPermissions(missing, ASK)
            return false
        }
        return !asked()
    }

    /** Asks to keep the app out of battery optimisation where the phone has not been asked yet. */
    private fun asked(): Boolean {
        val question = PhoneSync.unoptimised(this) ?: return false
        try {
            startActivityForResult(question, UNOPTIMISED)
        } catch (missing: ActivityNotFoundException) {
            Log.w(TAG, "the phone offers no battery optimisation question: ${missing.message}")
            return false
        }
        return true
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == UNOPTIMISED) launchTwa()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != ASK) return
        PhoneSync.all.forEach { it.request(this) }
        if (!asked()) launchTwa()
    }

    override fun getLaunchingUrl(): Uri =
        "${Installation.current(this)}${Installation.pathOf(intent.getStringExtra(PATH))}".toUri()

    override fun createTwaLauncher(): TwaLauncher {
        val shared = shared() ?: return super.createTwaLauncher()
        return Sharing(
            this,
            LauncherActivityMetadata.parse(this).launchingBrowser,
            SessionStore.makeSessionId(taskId),
            checkNotNull(Installation.current(this)),
            shared,
        )
    }

    /** What another app shares, its files only those it let the app read, which pass on to Chrome. */
    private fun shared(): ShareData? {
        val given = SharingUtils.retrieveShareDataFromIntent(intent) ?: return null
        val uris = given.uris.orEmpty().filter(::isTrustedContentUri)
        if (uris.isEmpty() && given.title == null && given.text == null) return null
        return ShareData(given.title, given.text, uris)
    }

    private fun ask(current: String?) {
        setContentView(R.layout.address)
        val address = findViewById<EditText>(R.id.address)
        val error = findViewById<TextView>(R.id.error)
        val open = findViewById<Button>(R.id.open)
        current?.let { address.setText(it.removePrefix("https://")) }
        fun shown(message: String) {
            error.text = message
            error.visibility = View.VISIBLE
            open.isEnabled = true
        }
        fun go() {
            val origin = Installation.originOf(address.text.toString())
                ?: return shown(getString(R.string.address_invalid))
            open.isEnabled = false
            thread {
                val answered = try {
                    if (Installation.answers(origin)) null else getString(R.string.address_not_ponistra)
                } catch (failed: IOException) {
                    getString(R.string.unreachable, failed.message)
                }
                runOnUiThread {
                    if (answered != null) return@runOnUiThread shown(answered)
                    Installation.choose(this, origin)
                    launchTwa()
                }
            }
        }
        open.setOnClickListener { go() }
        address.setOnEditorActionListener { _, action, _ ->
            (action == EditorInfo.IME_ACTION_GO).also { if (it) go() }
        }
    }

    companion object {
        const val PATH = "biz.boskovic.ponistra.PATH"
        const val CHANGE = "biz.boskovic.ponistra.CHANGE"
        private const val TAG = "Ponistra"
        private const val ASK = 1
        private const val UNOPTIMISED = 2
    }
}
