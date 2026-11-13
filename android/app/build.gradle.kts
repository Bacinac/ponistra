import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "biz.boskovic.ponistra"
    compileSdk {
        version = release(libs.versions.compileSdk.get().toInt()) {
            minorApiLevel = libs.versions.compileSdkMinor.get().toInt()
        }
    }
    buildToolsVersion = libs.versions.buildTools.get()
    defaultConfig {
        applicationId = "biz.boskovic.ponistra"
        minSdk = libs.versions.minSdk.get().toInt()
        targetSdk = libs.versions.targetSdk.get().toInt()
        versionCode = providers.gradleProperty("app.versionCode").orNull?.toInt()
            ?: throw GradleException("app.versionCode is not set; build through android/build.sh")
        versionName = providers.gradleProperty("app.versionName").orNull
            ?: throw GradleException("app.versionName is not set; build through android/build.sh")
    }
    compileOptions {
        val java = JavaVersion.toVersion(libs.versions.java.get())
        sourceCompatibility = java
        targetCompatibility = java
    }
    signingConfigs {
        create("release") {
            val file = rootProject.file("keystore/keystore.properties")
            if (file.exists()) {
                val keys = Properties().apply { file.inputStream().use { load(it) } }
                storeFile = rootProject.file(keys.getProperty("storeFile"))
                storePassword = keys.getProperty("storePassword")
                keyAlias = keys.getProperty("keyAlias")
                keyPassword = keys.getProperty("keyPassword")
            }
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
            signingConfig = signingConfigs.getByName("release")
        }
    }
    lint {
        // targetSdk stays below 37: API 37 makes reaching the local network a runtime permission,
        // and an installation may well resolve to an address on the LAN.
        disable += "OldTargetApi"
        abortOnError = true
        warningsAsErrors = true
        checkReleaseBuilds = true
    }
    testOptions.unitTests.all { it.useJUnitPlatform() }
}

kotlin {
    compilerOptions.allWarningsAsErrors = true
}

dependencies {
    implementation(libs.androidx.core)
    implementation(libs.browser.helper)
    implementation(libs.work.runtime)
    implementation(libs.okhttp)
    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
}
