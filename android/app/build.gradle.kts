import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import java.nio.file.Files

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val sharedWebDirectory = rootProject.file("../src/sugarglider/web/static")
val shellAssetList = rootProject.file("shell-assets.txt")
val shellAssetPaths = shellAssetList.readLines().filter { it.isNotBlank() && !it.startsWith('#') }
require(shellAssetPaths.isNotEmpty() && shellAssetPaths.distinct().size == shellAssetPaths.size)
require(shellAssetPaths.all { path ->
    !path.startsWith('/') && '\\' !in path && path.split('/').none { it in setOf("", ".", "..") }
})
val bundledShellDirectory = layout.buildDirectory.dir("generated/bundled-shell")
val bundleSharedWebShell by tasks.registering(Sync::class) {
    inputs.file(shellAssetList)
    from(sharedWebDirectory) { include(shellAssetPaths); into("web") }
    from(shellAssetList)
    into(bundledShellDirectory)
    doFirst {
        require(shellAssetPaths.all { path ->
            val source = sharedWebDirectory.resolve(path)
            source.isFile && !Files.isSymbolicLink(source.toPath())
        }) { "The declared shared Android shell is incomplete." }
    }
}

android {
    namespace = "io.github.victorgabillon.sugarglider"
    compileSdk = 36
    buildToolsVersion = "36.0.0"

    defaultConfig {
        applicationId = "io.github.victorgabillon.sugarglider"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("boolean", "ALLOW_HTTP", "false")
        ndk.abiFilters += "arm64-v8a"
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            buildConfigField("boolean", "ALLOW_HTTP", "true")
        }
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }

    sourceSets.getByName("main").assets.srcDir(bundledShellDirectory)
}

tasks.named("preBuild").configure { dependsOn(bundleSharedWebShell) }

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
        freeCompilerArgs.add("-Xjsr305=strict")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.webkit:webkit:1.15.0")

    implementation("io.github.rallista:valhalla-mobile:0.5.1")
    implementation("io.github.rallista:valhalla-models:0.1.1")
    implementation("io.github.rallista:valhalla-models-config:0.1.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.moshi:moshi-kotlin:1.15.1")
    testImplementation("org.json:json:20250517")
}
