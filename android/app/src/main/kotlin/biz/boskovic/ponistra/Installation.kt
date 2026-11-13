package biz.boskovic.ponistra

import android.accounts.Account
import android.accounts.AccountManager
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.core.content.edit
import java.io.IOException
import java.net.URI
import java.net.URISyntaxException
import java.net.URLDecoder
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONException
import org.json.JSONObject

/** The PONISTRA installation the app opens, and the accounts the phone signs in to it with: each an
 *  app password Android keeps, sent as a bearer token (D26). */
object Installation {
    const val ACCOUNT_TYPE = "biz.boskovic.ponistra"
    private const val TAG = "Ponistra"
    private const val PREFERENCES = "installation"
    const val ORIGIN = "origin"
    private const val EMAIL = "email"
    private const val NAME = 150
    private val JSON = "application/json".toMediaType()

    val client = OkHttpClient()

    class Link(val origin: String, val code: String)

    /** The installation no longer takes the link's pairing code: it lapsed, or was claimed already. */
    class Lapsed : IOException("the pairing code lapsed")

    /** The origin an address names, https alone: a Trusted Web Activity opens nothing else. */
    fun originOf(address: String): String? {
        val text = address.trim()
        if (text.isEmpty() || text.any(Char::isWhitespace)) return null
        val uri = try {
            URI(if ("://" in text) text else "https://$text")
        } catch (_: URISyntaxException) {
            return null
        }
        val host = uri.host?.lowercase() ?: return null
        if (uri.scheme?.lowercase() != "https" || uri.rawUserInfo != null) return null
        return if (uri.port == -1) "https://$host" else "https://$host:${uri.port}"
    }

    /** What a PONISTRA page hands the app to connect the phone: `ponistra://connect?origin=…&code=…`. */
    fun linkOf(uri: String): Link? {
        val parsed = try {
            URI(uri)
        } catch (_: URISyntaxException) {
            return null
        }
        if (parsed.scheme != "ponistra" || parsed.host != "connect") return null
        val given = parsed.rawQuery.orEmpty().split('&').mapNotNull { pair ->
            pair.split('=', limit = 2).takeIf { it.size == 2 }
                ?.let { (key, value) -> key to URLDecoder.decode(value, "UTF-8") }
        }.toMap()
        val origin = given["origin"]?.let(::originOf) ?: return null
        val code = given["code"]?.trim()?.takeIf(String::isNotEmpty) ?: return null
        return Link(origin, code)
    }

    /** A path of the installation to open, never one that would leave its origin. */
    fun pathOf(given: String?): String = given?.takeIf { it.startsWith("/") && !it.startsWith("//") } ?: "/"

    fun current(context: Context): String? = preferences(context).getString(ORIGIN, null)

    fun choose(context: Context, origin: String) = preferences(context).edit { putString(ORIGIN, origin) }

    /** Whether a PONISTRA answers at the origin: every installation tells its version. */
    fun answers(origin: String): Boolean = try {
        JSONObject(text(Request.Builder().url("$origin/api/version").build())).has("version")
    } catch (_: JSONException) {
        false
    }

    /** Signs the phone in with the app password the link brings, as the account of the user it
     *  belongs to, and names the phone for the list of the user's app passwords; the email. */
    fun connect(context: Context, link: Link): String {
        val claim = JSONObject().put("code", link.code).toString().toRequestBody(JSON)
        val password = client.newCall(Request.Builder().url("${link.origin}/api/device/claim").post(claim).build())
            .execute().use { response ->
                if (response.code == 400) throw Lapsed()
                if (!response.isSuccessful) throw IOException("HTTP ${response.code} from ${response.request.url}")
                JSONObject(response.body.string()).getString("password")
            }
        val email = JSONObject(text(device(link.origin, password).build())).getString("email")
        val named = JSONObject().put("name", phoneName()).toString().toRequestBody(JSON)
        text(device(link.origin, password).patch(named).build())
        val manager = AccountManager.get(context)
        val accounts = manager.getAccountsByType(ACCOUNT_TYPE)
        val kept = accounts.firstOrNull {
            manager.getUserData(it, ORIGIN) == link.origin && manager.getUserData(it, EMAIL) == email
        }
        val account = if (kept != null) {
            val replaced = manager.getPassword(kept)
            manager.setPassword(kept, password)
            if (replaced != null) signOut(link.origin, replaced)
            kept
        } else {
            val name = if (accounts.any { it.name == email }) "$email (${URI(link.origin).host})" else email
            val data = Bundle().apply {
                putString(ORIGIN, link.origin)
                putString(EMAIL, email)
            }
            Account(name, ACCOUNT_TYPE).also {
                if (!manager.addAccountExplicitly(it, password, data)) throw IOException("Android did not add the account $name")
            }
        }
        PhoneSync.enabled(manager, account)
        choose(context, link.origin)
        return email
    }

    /** Ends the account's app password at its installation, as the phone gives the account up. */
    fun signOut(context: Context, account: Account) {
        val manager = AccountManager.get(context)
        val origin = manager.getUserData(account, ORIGIN) ?: return
        signOut(origin, manager.getPassword(account) ?: return)
    }

    private fun signOut(origin: String, password: String) {
        try {
            text(device(origin, password).delete().build())
        } catch (failed: IOException) {
            Log.w(TAG, "$origin still holds the phone's app password: ${failed.message}")
        }
    }

    private fun device(origin: String, password: String) =
        Request.Builder().url("$origin/api/device").header("Authorization", "Bearer $password")

    private fun phoneName(): String {
        val maker = Build.MANUFACTURER.replaceFirstChar { it.titlecase() }
        val model = Build.MODEL
        return (if (model.startsWith(maker, ignoreCase = true)) model else "$maker $model").take(NAME)
    }

    fun text(request: Request): String = client.newCall(request).execute().use { response ->
        if (!response.isSuccessful) throw IOException("HTTP ${response.code} from ${request.url}")
        response.body.string()
    }

    private fun preferences(context: Context) = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
}
