package biz.boskovic.ponistra

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.core.content.IntentCompat
import androidx.core.content.edit
import androidx.core.content.pm.PackageInfoCompat
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import okhttp3.Request
import org.json.JSONException
import org.json.JSONObject

class UpdateRejected(message: String) : IOException(message)

/** The app as its installation serves it beside the web app: `/android/ponistra.json` says which
 *  version is there, `/android/ponistra.apk` is the file. A newer one is fetched in the background,
 *  checked (digest, package, version, signer) and installed by the app itself: without a word where
 *  Android lets an app update itself, and from Android 14 only while the app is out of sight; where
 *  Android asks the user, through a notification they tap. */
class Updater(private val context: Context) {
    class Offer(val versionCode: Long, val sha256: String)

    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val file = File(File(context.cacheDir, "updates"), "update.apk")
    private val installer = context.packageManager.packageInstaller

    /** Installs the newer version the installation offers, unless the same one waits already: for
     *  the app to leave the screen, or for the user. One that has waited a day is given again. */
    fun fetch(origin: String) {
        val offer = offer(origin) ?: return
        val waiting = installer.mySessions
        val since = System.currentTimeMillis() - preferences.getLong(GIVEN_AT, 0)
        if (waiting.isNotEmpty() && preferences.getLong(GIVEN, 0) == offer.versionCode && since < DAY) return
        waiting.forEach { installer.abandonSession(it.sessionId) }
        try {
            download(origin, offer)
            install()
        } finally {
            file.delete()
        }
        preferences.edit {
            putLong(GIVEN, offer.versionCode)
            putLong(GIVEN_AT, System.currentTimeMillis())
        }
    }

    private fun install() {
        val parameters = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
            setAppPackageName(context.packageName)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
            }
        }
        val id = installer.createSession(parameters)
        try {
            installer.openSession(id).use { session ->
                session.openWrite(file.name, 0, file.length()).use { out ->
                    file.inputStream().use { it.copyTo(out) }
                    session.fsync(out)
                }
                // Android puts the session's outcome into the intent, so it must stay mutable.
                val told = PendingIntent.getBroadcast(
                    context,
                    id,
                    Intent(context, UpdateReceiver::class.java),
                    PendingIntent.FLAG_MUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
                ).intentSender
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                    val away = PackageInstaller.InstallConstraints.Builder()
                        .setAppNotForegroundRequired()
                        .setAppNotInteractingRequired()
                        .build()
                    installer.commitSessionAfterInstallConstraintsAreMet(id, told, away, DAY)
                } else {
                    session.commit(told)
                }
            }
        } catch (failure: IOException) {
            installer.abandonSession(id)
            throw failure
        }
    }

    private fun offer(origin: String): Offer? {
        val request = Request.Builder().url("$origin/android/ponistra.json").build()
        val said = Installation.client.newCall(request).execute().use { response ->
            // An installation whose release carries no app.
            if (response.code == 404) return null
            if (!response.isSuccessful) throw IOException("HTTP ${response.code} from ${request.url}")
            response.body.string()
        }
        val offer = try {
            JSONObject(said).let {
                Offer(it.getLong("versionCode"), it.getString("sha256").lowercase())
            }
        } catch (bad: JSONException) {
            throw UpdateRejected("${request.url} is not a version: ${bad.message}")
        }
        return offer.takeIf { it.versionCode > installed(context).versionCode() }
    }

    private fun download(origin: String, offer: Offer) {
        file.parentFile?.mkdirs()
        val request = Request.Builder().url("$origin/android/ponistra.apk?v=${offer.versionCode}").build()
        Installation.client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("HTTP ${response.code} from ${request.url}")
            file.outputStream().use { out -> response.body.byteStream().copyTo(out) }
        }
        verify(offer, sha256(file), Apk(installed(context, PackageManager.GET_SIGNING_CERTIFICATES))) {
            archived(file)?.let(::Apk)
        }
    }

    private fun archived(file: File): PackageInfo? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            context.packageManager.getPackageArchiveInfo(
                file.path,
                PackageManager.PackageInfoFlags.of(PackageManager.GET_SIGNING_CERTIFICATES.toLong()),
            )
        } else {
            @Suppress("DEPRECATION")
            context.packageManager.getPackageArchiveInfo(file.path, PackageManager.GET_SIGNING_CERTIFICATES)
        }

    class Apk(val name: String, val versionCode: Long, val signers: Set<String>) {
        constructor(info: PackageInfo) : this(
            info.packageName,
            info.versionCode(),
            info.signingInfo?.apkContentsSigners.orEmpty().map { it.toCharsString() }.toSet(),
        )
    }

    companion object {
        private const val PREFERENCES = "updates"
        private const val GIVEN = "given"
        private const val GIVEN_AT = "given_at"
        private const val DAY = 24 * 60 * 60 * 1000L

        fun installed(context: Context, flags: Int = 0): PackageInfo =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                context.packageManager.getPackageInfo(
                    context.packageName,
                    PackageManager.PackageInfoFlags.of(flags.toLong()),
                )
            } else {
                @Suppress("DEPRECATION")
                context.packageManager.getPackageInfo(context.packageName, flags)
            }

        private fun PackageInfo.versionCode(): Long = PackageInfoCompat.getLongVersionCode(this)

        internal fun verify(offer: Offer, digest: String, installed: Apk, archive: () -> Apk?) {
            if (digest != offer.sha256) throw UpdateRejected("the digest is not the one offered")
            val arrived = archive() ?: throw UpdateRejected("not a readable package")
            if (arrived.name != installed.name) throw UpdateRejected("package ${arrived.name} is not ${installed.name}")
            if (arrived.versionCode != offer.versionCode) {
                throw UpdateRejected("package is version ${arrived.versionCode}, not ${offer.versionCode}")
            }
            if (arrived.signers.isEmpty() || arrived.signers != installed.signers) {
                throw UpdateRejected("package is not signed by this app's key")
            }
        }

        internal fun sha256(file: File): String {
            val digest = MessageDigest.getInstance("SHA-256")
            file.inputStream().use { input ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    digest.update(buffer, 0, read)
                }
            }
            return digest.digest().joinToString("") { "%02x".format(it) }
        }
    }
}

/** Fetches a newer app from the installation: when the app opens, after each sync and twice a
 *  day, whichever comes first. */
class UpdateWorker(context: Context, parameters: WorkerParameters) : Worker(context, parameters) {
    override fun doWork(): Result {
        val origin = Installation.current(applicationContext) ?: return Result.success()
        return try {
            Updater(applicationContext).fetch(origin)
            Result.success()
        } catch (rejected: UpdateRejected) {
            Log.e(TAG, "the update from $origin is refused: ${rejected.message}")
            Result.failure()
        } catch (failed: IOException) {
            Log.w(TAG, "no update from $origin: ${failed.message}")
            Result.failure()
        }
    }

    companion object {
        private const val TAG = "Ponistra"
        private const val PERIOD = 12L

        fun schedule(context: Context) {
            val network = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
            val work = WorkManager.getInstance(context)
            work.enqueueUniqueWork(
                "update",
                ExistingWorkPolicy.KEEP,
                OneTimeWorkRequestBuilder<UpdateWorker>().setConstraints(network).build(),
            )
            work.enqueueUniquePeriodicWork(
                "updates",
                ExistingPeriodicWorkPolicy.KEEP,
                PeriodicWorkRequestBuilder<UpdateWorker>(PERIOD, TimeUnit.HOURS).setConstraints(network).build(),
            )
        }
    }
}

/** What Android says of an update the app gave it: the screen where the user confirms it, which
 *  waits in a notification as the app is in the background, or why it failed. */
class UpdateReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE).orEmpty()
        when {
            status == PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val confirm = IntentCompat.getParcelableExtra(intent, Intent.EXTRA_INTENT, Intent::class.java) ?: return
                notify(
                    context,
                    context.getString(R.string.update_ready),
                    PendingIntent.getActivity(
                        context,
                        NOTICE,
                        confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
                    ),
                )
            }
            status == PackageInstaller.STATUS_SUCCESS ->
                context.getSystemService(NotificationManager::class.java).cancel(NOTICE)
            status == PackageInstaller.STATUS_FAILURE_ABORTED -> Log.i(TAG, "the update was abandoned: $message")
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE &&
                status == PackageInstaller.STATUS_FAILURE_TIMEOUT ->
                Log.i(TAG, "the app stayed in sight for a day, the update is given again")
            else -> {
                Log.e(TAG, "the update failed ($status): $message")
                notify(context, context.getString(R.string.update_failed, message), null)
            }
        }
    }

    private fun notify(context: Context, title: String, open: PendingIntent?) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "notifications are closed to the app: $title")
            return
        }
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, context.getString(R.string.updates_channel), NotificationManager.IMPORTANCE_DEFAULT),
        )
        manager.notify(
            NOTICE,
            Notification.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.brand_badge)
                .setContentTitle(title)
                .setContentIntent(open)
                .setAutoCancel(true)
                .build(),
        )
    }

    companion object {
        private const val TAG = "Ponistra"
        private const val CHANNEL = "updates"
        private const val NOTICE = 3
    }
}
