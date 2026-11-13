package biz.boskovic.ponistra

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import java.io.IOException
import kotlin.concurrent.thread
import org.json.JSONException

/** Connects the phone with the app password its pairing code claims from a PONISTRA page, asks for
 *  the phone's contacts to hold the address book in, then opens the page that lists the phone. */
class ConnectActivity : Activity() {
    private var email: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.connect)
        val link = intent.dataString?.let(Installation::linkOf) ?: return failed(getString(R.string.connect_invalid))
        thread {
            val outcome = try {
                Result.success(Installation.connect(this, link))
            } catch (failure: IOException) {
                Result.failure(failure)
            } catch (failure: JSONException) {
                Result.failure(failure)
            }
            runOnUiThread {
                outcome.fold(
                    onSuccess = {
                        email = it
                        requestPermissions(PhoneSync.permissions(), ASK)
                    },
                    onFailure = {
                        failed(
                            if (it is Installation.Lapsed) getString(R.string.connect_lapsed)
                            else getString(R.string.connect_failed, it.message),
                        )
                    },
                )
            }
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != ASK) return
        PhoneSync.all.forEach { it.request(this) }
        Toast.makeText(this, getString(R.string.connected, email), Toast.LENGTH_LONG).show()
        startActivity(Intent(this, MainActivity::class.java).putExtra(MainActivity.PATH, "/settings/app-passwords"))
        finish()
    }

    private fun failed(message: String) {
        findViewById<ProgressBar>(R.id.progress).visibility = View.GONE
        findViewById<TextView>(R.id.message).text = message
        findViewById<Button>(R.id.close).apply {
            visibility = View.VISIBLE
            setOnClickListener { finish() }
        }
    }

    private companion object {
        const val ASK = 1
    }
}
