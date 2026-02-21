package com.sikwin.app.data.prefs

import android.content.Context
import android.content.SharedPreferences
import androidx.core.os.LocaleListCompat
import androidx.appcompat.app.AppCompatDelegate

class LanguagePreferences(private val context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("gunduata_prefs", Context.MODE_PRIVATE)

    companion object {
        private const val KEY_APP_LOCALE = "app_locale"
    }

    /**
     * @param localeTag BCP 47 language tag (e.g. "en", "hi", "bn"). Empty string = system default.
     */
    fun setAppLocale(localeTag: String) {
        prefs.edit().putString(KEY_APP_LOCALE, localeTag).apply()
    }

    fun getAppLocale(): String {
        return prefs.getString(KEY_APP_LOCALE, "") ?: ""
    }

    /**
     * Apply the saved locale. Call from MainActivity.onCreate before setContent.
     * Defaults to English if no preference saved.
     */
    fun applySavedLocale() {
        val tag = getAppLocale().ifBlank { "en" }
        AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(tag))
    }
}
