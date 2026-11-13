package biz.boskovic.ponistra

import android.content.Context
import androidx.browser.customtabs.CustomTabsCallback
import androidx.browser.trusted.TrustedWebActivityIntentBuilder
import androidx.browser.trusted.sharing.ShareData
import androidx.browser.trusted.sharing.ShareTarget
import com.google.androidbrowserhelper.trusted.SharedPreferencesTokenStore
import com.google.androidbrowserhelper.trusted.TwaLauncher
import com.google.androidbrowserhelper.trusted.splashscreens.SplashScreenStrategy

/** Opens the web app with what another app shared, which Chrome posts to the installation's share
 *  target, the one its manifest names, for the service worker to keep (D26-4). The library posts
 *  only to a target named in full in the app's own manifest, while one app serves every
 *  installation. */
class Sharing(
    context: Context,
    browser: String?,
    session: Int?,
    origin: String,
    private val shared: ShareData,
) : TwaLauncher(context, browser, session, SharedPreferencesTokenStore(context)) {
    private val target = ShareTarget(
        "$origin/share",
        ShareTarget.METHOD_POST,
        ShareTarget.ENCODING_TYPE_MULTIPART,
        ShareTarget.Params("title", "text", listOf(ShareTarget.FileFormField("files", listOf("*/*")))),
    )

    override fun launch(
        builder: TrustedWebActivityIntentBuilder,
        callback: CustomTabsCallback?,
        splash: SplashScreenStrategy?,
        completion: Runnable?,
        fallback: FallbackStrategy,
    ) = super.launch(builder.setShareParams(target, shared), callback, splash, completion, fallback)
}
