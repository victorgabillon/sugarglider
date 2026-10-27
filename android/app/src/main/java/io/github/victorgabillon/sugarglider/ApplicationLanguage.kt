package io.github.victorgabillon.sugarglider

import android.content.Context
import android.content.res.Configuration
import android.view.ContextThemeWrapper
import java.util.Locale

/** UI-only preference. Applying it never recreates an Activity or WebView. */
internal object ApplicationLanguage {
    private const val PREFERENCES = "sugarglider_ui"
    private const val KEY = "language"

    fun valid(value: String): Boolean = value == "fr" || value == "en"
    fun normalized(value: Any?): String = if (value == "en") "en" else "fr"
    fun current(context: Context): String = try {
        normalized(context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).all[KEY])
    } catch (_: Exception) { "fr" }

    fun select(context: Context, language: String): Boolean {
        if (!valid(language)) return false
        return try {
            context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).edit().putString(KEY, language).apply()
            true
        } catch (_: Exception) { false }
    }

    fun context(context: Context): Context {
        val configuration = Configuration(context.resources.configuration)
        configuration.setLocale(Locale.forLanguageTag(current(context)))
        // Keep the Activity as the base so dialogs inherit its window token.
        // A standalone configuration context loses that Activity window manager.
        return ContextThemeWrapper(context, context.theme).apply {
            applyOverrideConfiguration(configuration)
        }
    }

    fun text(context: Context, id: Int, vararg args: Any): String = context(context).getString(id, *args)
}
