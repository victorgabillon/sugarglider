package io.github.victorgabillon.sugarglider

import android.app.Activity
import android.app.AlertDialog
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/** The full native disclosure and its explicit published-policy action. */
internal object PrivacyDetailsDialog {
    fun show(activity: Activity, openPolicy: (() -> Unit)?): AlertDialog {
        val context = ApplicationLanguage.context(activity)
        fun dp(value: Int): Int = (value * context.resources.displayMetrics.density).toInt()
        val body = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), 0, dp(20), dp(12))
        }
        val content = TextView(context).apply {
            tag = "privacy-description"
            setText(R.string.privacy_description)
            textSize = 16f
            setPadding(0, dp(12), 0, dp(12))
        }
        // The disclosure scrolls; actions keep their measured height. Android's
        // standard button panel clips the long policy label on narrow windows.
        body.addView(ScrollView(context).apply {
            tag = "privacy-scroll"
            addView(content)
        },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        val dialog = AlertDialog.Builder(context)
            .setTitle(R.string.privacy_title)
            .setView(body)
            .create()
        fun action(label: Int, name: String, perform: () -> Unit) {
            body.addView(Button(context).apply {
                tag = name
                setText(label)
                isAllCaps = false
                setSingleLine(false)
                maxLines = Int.MAX_VALUE
                ellipsize = null
                minimumHeight = dp(48)
                setPadding(dp(12), dp(8), dp(12), dp(8))
                setOnClickListener { dialog.dismiss(); perform() }
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        if (openPolicy != null) action(R.string.privacy_online, "privacy-policy", openPolicy)
        action(R.string.privacy_close, "privacy-close") { }
        dialog.show()
        return dialog
    }
}
