plugins {
    alias(libs.plugins.android.application) apply false
    // Only to choose the Kotlin that AGP's built-in Kotlin compiles with.
    alias(libs.plugins.kotlin.android) apply false
}
