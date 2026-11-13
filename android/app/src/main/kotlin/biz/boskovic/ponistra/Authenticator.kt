package biz.boskovic.ponistra

import android.accounts.AbstractAccountAuthenticator
import android.accounts.Account
import android.accounts.AccountAuthenticatorResponse
import android.accounts.AccountManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.IBinder

/** The accounts Android lists for the app. One is added only by connecting the phone from a
 *  PONISTRA page, so adding one from the phone's settings opens PONISTRA; removing one signs the
 *  phone out at its installation. */
class Authenticator(private val context: Context) : AbstractAccountAuthenticator(context) {
    override fun addAccount(
        response: AccountAuthenticatorResponse?,
        accountType: String?,
        authTokenType: String?,
        requiredFeatures: Array<out String>?,
        options: Bundle?,
    ): Bundle = Bundle().apply { putParcelable(AccountManager.KEY_INTENT, Intent(context, MainActivity::class.java)) }

    override fun getAccountRemovalAllowed(response: AccountAuthenticatorResponse?, account: Account): Bundle {
        Installation.signOut(context, account)
        return answer(true)
    }

    override fun hasFeatures(
        response: AccountAuthenticatorResponse?,
        account: Account?,
        features: Array<out String>?,
    ): Bundle = answer(features.isNullOrEmpty())

    override fun editProperties(response: AccountAuthenticatorResponse?, accountType: String?): Bundle? = null

    override fun confirmCredentials(response: AccountAuthenticatorResponse?, account: Account?, options: Bundle?): Bundle? = null

    override fun getAuthToken(
        response: AccountAuthenticatorResponse?,
        account: Account?,
        authTokenType: String?,
        options: Bundle?,
    ): Bundle? = null

    override fun getAuthTokenLabel(authTokenType: String?): String? = null

    override fun updateCredentials(
        response: AccountAuthenticatorResponse?,
        account: Account?,
        authTokenType: String?,
        options: Bundle?,
    ): Bundle? = null

    private fun answer(yes: Boolean) = Bundle().apply { putBoolean(AccountManager.KEY_BOOLEAN_RESULT, yes) }
}

class AuthenticatorService : Service() {
    private val authenticator by lazy { Authenticator(this) }

    override fun onBind(intent: Intent?): IBinder? = authenticator.iBinder
}
