plugins {
    id("com.android.application")
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

    // NPatch 模块不需要打包 xposed_init 之外的额外逻辑，保持精简
    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module")
    }
}

dependencies {
    // LSPosed API：只用来做 Xposed 入口判断，NPatch 兼容
    compileOnly("de.robv.android.xposed:api:82")
}

// 把 assets/xposed_init 打进去，NPatch 靠它找入口类
tasks.register<Copy>("mergeXposedInit") {
    from("src/main/assets")
    into(layout.buildDirectory.dir("intermediates/assets/release"))
}
