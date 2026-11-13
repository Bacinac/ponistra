package biz.boskovic.ponistra

import android.net.Uri
import androidx.core.net.toUri
import com.google.androidbrowserhelper.trusted.ManageDataLauncherActivity

/** Chrome's settings of the installation's site, which the launcher's "Site Settings" shortcut
 *  opens: the address is the one the phone chose, which no manifest knows. */
class SiteSettings : ManageDataLauncherActivity() {
    override fun getDefaultUrlForManagingSpace(): Uri? = Installation.current(this)?.toUri()
}
