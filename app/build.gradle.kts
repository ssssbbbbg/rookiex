plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "com.rain.rookiex"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.rain.rookiex"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module")
    }
}

dependencies {
    // Xposed API 由 NPatch/LSPatch 运行时提供，编译期只做引用
    compileOnly("de.robv.android.xposed:api:82")
}
