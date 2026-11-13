package biz.boskovic.ponistra

import android.Manifest
import android.annotation.SuppressLint
import android.accounts.Account
import android.accounts.AccountManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ContentResolver
import android.content.Context
import android.content.Intent
import android.content.OperationApplicationException
import android.content.SyncResult
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.os.RemoteException
import android.provider.Settings
import android.util.Log
import androidx.annotation.StringRes
import androidx.core.content.edit
import java.io.IOException
import okhttp3.Request
import okhttp3.Response
import org.json.JSONException

/** A sync of the account with one of the phone's own apps (D26): the access it needs, on from
 *  the moment the account has it, and a notification that opens the app's settings where the
 *  access is closed. */
abstract class PhoneSync(
    val authority: String,
    private val reads: Array<String>,
    private val notice: Int,
    private val channel: String,
    @param:StringRes private val channelName: Int,
    @param:StringRes private val refusedTitle: Int,
    @param:StringRes private val refusedText: Int,
) {
    fun granted(context: Context) =
        reads.all { context.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }

    fun enable(account: Account) {
        ContentResolver.setSyncAutomatically(account, authority, true)
        ContentResolver.addPeriodicSync(account, authority, Bundle.EMPTY, PERIOD)
    }

    fun request(context: Context) {
        AccountManager.get(context).getAccountsByType(Installation.ACCOUNT_TYPE).forEach {
            ContentResolver.requestSync(
                it,
                authority,
                Bundle().apply {
                    putBoolean(ContentResolver.SYNC_EXTRAS_MANUAL, true)
                    putBoolean(ContentResolver.SYNC_EXTRAS_EXPEDITED, true)
                },
            )
        }
    }

    /** One sync of the account with the installation it connected to, as Android counts what
     *  went wrong. */
    fun performed(context: Context, account: Account, result: SyncResult, sync: (origin: String, password: String) -> Unit) {
        UpdateWorker.schedule(context)
        if (!granted(context)) {
            refused(context)
            result.stats.numAuthExceptions++
            return
        }
        val manager = AccountManager.get(context)
        val origin = manager.getUserData(account, Installation.ORIGIN) ?: return
        val password = manager.getPassword(account) ?: return
        try {
            sync(origin, password)
        } catch (failure: SignedOut) {
            failed("${account.name} is signed out at $origin", failure)
            result.stats.numAuthExceptions++
        } catch (failure: IOException) {
            failed("$origin did not answer", failure)
            result.stats.numIoExceptions++
        } catch (failure: JSONException) {
            failed("$origin answered what the app does not read", failure)
            result.stats.numParseExceptions++
        } catch (failure: RemoteException) {
            failed("the phone's $authority refused a change", failure)
            result.databaseError = true
        } catch (failure: OperationApplicationException) {
            failed("the phone's $authority refused a change", failure)
            result.databaseError = true
        }
    }

    /** Says the phone's app is closed to PONISTRA, and opens its settings to allow it. */
    fun refused(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "$authority and notifications are both closed to the app")
            return
        }
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(channel, context.getString(channelName), NotificationManager.IMPORTANCE_DEFAULT),
        )
        val settings = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
        val open = PendingIntent.getActivity(context, notice, settings, PendingIntent.FLAG_IMMUTABLE)
        manager.notify(
            notice,
            Notification.Builder(context, channel)
                .setSmallIcon(R.drawable.brand_badge)
                .setContentTitle(context.getString(refusedTitle))
                .setContentText(context.getString(refusedText))
                .setStyle(Notification.BigTextStyle().bigText(context.getString(refusedText)))
                .setContentIntent(open)
                .setAutoCancel(true)
                .build(),
        )
    }

    companion object {
        private const val TAG = "Ponistra"
        private const val SYNCS = "syncs"
        private const val PREFERENCES = "syncs"
        private const val UNOPTIMISED = "unoptimised_asked"
        // Android runs a periodic sync no more often than every 15 minutes.
        private const val PERIOD = 15 * 60L

        val all: List<PhoneSync> get() = listOf(ContactsSync, CalendarSync)

        /** What the app asks for as the phone connects: every sync's access, and notifications to
         *  say when one is closed. */
        fun permissions(): Array<String> {
            val reads = all.flatMap { it.reads.toList() }.toTypedArray()
            return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) reads + Manifest.permission.POST_NOTIFICATIONS else reads
        }

        fun enabled(manager: AccountManager, account: Account) {
            all.forEach { it.enable(account) }
            manager.setUserData(account, SYNCS, all.joinToString(",") { it.authority })
        }

        /** Turns on the syncs an account connected before them has not had yet, and gives the
         *  access they need that the app does not hold. */
        fun adopted(context: Context): Array<String> {
            val manager = AccountManager.get(context)
            val added = mutableSetOf<PhoneSync>()
            for (account in manager.getAccountsByType(Installation.ACCOUNT_TYPE)) {
                val had = manager.getUserData(account, SYNCS)?.split(",").orEmpty()
                val new = all.filter { it.authority !in had }
                if (new.isEmpty()) continue
                new.forEach { it.enable(account) }
                manager.setUserData(account, SYNCS, all.joinToString(",") { it.authority })
                added += new
            }
            return added.filterNot { it.granted(context) }.flatMap { it.reads.toList() }.toTypedArray()
        }

        /** Android's question to keep the app out of battery optimisation, asked once while an
         *  account syncs: an optimised app left in the background is frozen with its network closed
         *  (Samsung), and Android starts no sync without network, so none ran until it was opened. */
        // The app is not on Google Play, whose policy on this question the lint check stands for.
        @SuppressLint("BatteryLife")
        fun unoptimised(context: Context): Intent? {
            val power = context.getSystemService(PowerManager::class.java)
            val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            if (power.isIgnoringBatteryOptimizations(context.packageName) || preferences.getBoolean(UNOPTIMISED, false)) return null
            if (AccountManager.get(context).getAccountsByType(Installation.ACCOUNT_TYPE).isEmpty()) return null
            preferences.edit { putBoolean(UNOPTIMISED, true) }
            return Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.fromParts("package", context.packageName, null))
        }

        fun failed(message: String, failure: Exception) = Log.w(TAG, "$message: ${failure.message}", failure)

        /** The request made with the account's app password; SignedOut where it no longer
         *  holds. */
        fun call(password: String, request: Request.Builder): Response {
            val answer = Installation.client.newCall(request.header("Authorization", "Bearer $password").build()).execute()
            if (answer.code == 401) {
                answer.close()
                throw SignedOut()
            }
            return answer
        }

        fun unexpected(answer: Response) = IOException("HTTP ${answer.code} from ${answer.request.url}")
    }

    class SignedOut : IOException("the app password is no longer valid")
}
