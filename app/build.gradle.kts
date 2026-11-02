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

    signingConfigs {
        create("release") {
            // keystore 随仓库提交，CI 与本地都能直接签
            val ksFile = rootProject.file("keystore/rookiex.jks")
            if (ksFile.exists()) {
                storeFile = ksFile
                storePassword = System.getenv("KEYSTORE_PASSWORD") ?: "rain123456"
                keyAlias = System.getenv("KEY_ALIAS") ?: "rookiex"
                keyPassword = System.getenv("KEY_PASSWORD") ?: "rain123456"
                enableV1Signing = true
                enableV2Signing = true
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (rootProject.file("keystore/rookiex.jks").exists()) {
                signingConfig = signingConfigs.getByName("release")
            }
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
