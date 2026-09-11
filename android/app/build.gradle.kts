import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Release secrets are optional for unsigned validation and must live outside Git.
val externalSigningPath = providers.environmentVariable("SUGARGLIDER_ANDROID_SIGNING_PROPERTIES")
    .orNull
val externalSigning = externalSigningPath?.let { path ->
    val repository = rootProject.projectDir.parentFile.canonicalFile.toPath()
    val propertiesFile = File(path)
    require(propertiesFile.isAbsolute && propertiesFile.isFile) {
        "Android signing configuration must be an existing absolute external file"
    }
    require(!propertiesFile.canonicalFile.toPath().startsWith(repository)) {
        "Android signing configuration must be outside the repository"
    }
    val properties = Properties()
    try {
        propertiesFile.inputStream().use(properties::load)
    } catch (_: Exception) {
        throw GradleException("Unable to read external Android signing configuration")
    }
    val required = setOf("storeFile", "storePassword", "keyAlias", "keyPassword")
    require(properties.stringPropertyNames() == required &&
        required.all { !properties.getProperty(it).isNullOrBlank() }) {
        "Android signing configuration requires exactly storeFile, storePassword, keyAlias and keyPassword"
    }
    val keyStore = File(properties.getProperty("storeFile"))
    require(keyStore.isAbsolute && keyStore.isFile &&
        !keyStore.canonicalFile.toPath().startsWith(repository)) {
        "Android upload keystore must be an existing absolute file outside the repository"
    }
    properties
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
    }

    signingConfigs {
        externalSigning?.let { properties ->
            create("externalUpload") {
                storeFile = File(properties.getProperty("storeFile"))
                storePassword = properties.getProperty("storePassword")
                keyAlias = properties.getProperty("keyAlias")
                keyPassword = properties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            buildConfigField("boolean", "ALLOW_HTTP", "true")
            buildConfigField("boolean", "LOCAL_ROUTING_EXPERIMENT", "true")
            ndk.abiFilters += "arm64-v8a"
        }
        release {
            signingConfig = externalSigning?.let { signingConfigs.getByName("externalUpload") }
            isDebuggable = false
            buildConfigField("boolean", "LOCAL_ROUTING_EXPERIMENT", "false")
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
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
        freeCompilerArgs.add("-Xjsr305=strict")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.webkit:webkit:1.15.0")

    debugImplementation("io.github.rallista:valhalla-mobile:0.5.1")
    debugImplementation("io.github.rallista:valhalla-models:0.1.1")
    debugImplementation("io.github.rallista:valhalla-models-config:0.1.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20250517")
}
