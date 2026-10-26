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
    fun current(context: Context): String =
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).getString(KEY, "fr")
            ?.takeIf(::valid) ?: "fr"

    fun select(context: Context, language: String): Boolean {
        if (!valid(language)) return false
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).edit().putString(KEY, language).apply()
        return true
    }

    fun context(context: Context): Context {
        val configuration = Configuration(context.resources.configuration)
        configuration.setLocale(Locale.forLanguageTag(current(context)))
        return ContextThemeWrapper(context.createConfigurationContext(configuration), context.theme)
    }

    fun text(context: Context, id: Int, vararg args: Any): String = context(context).getString(id, *args)
}
