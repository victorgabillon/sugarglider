package io.github.victorgabillon.sugarglider

import android.app.Activity
import android.app.Application
import android.graphics.Rect
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.ScrollView
import android.widget.TextView
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.Shadows.shadowOf

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36], application = Application::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class PrivacyDetailsDialogTest {
    @Test fun frenchNormalText() = verify("fr", 1f)
    @Test fun englishNormalText() = verify("en", 1f)
    @Test fun frenchLargeText() = verify("fr", 2f)
    @Test fun englishLargeText() = verify("en", 2f)

    @Test fun closeWorksWithoutPublishedPolicy() {
        val controller = Robolectric.buildActivity(Activity::class.java).setup().visible()
        val dialog = PrivacyDetailsDialog.show(controller.get(), null)
        try {
            val decor = dialog.window!!.decorView
            assertNull(decor.findViewWithTag<Button>("privacy-policy"))
            decor.findViewWithTag<Button>("privacy-close").performClick()
            assertFalse(dialog.isShowing)
        } finally {
            dialog.dismiss()
            controller.pause().stop().destroy()
        }
    }

    private fun verify(language: String, fontScale: Float) {
        for ((width, height) in listOf(320 to 640, 372 to 767, 800 to 372)) {
            RuntimeEnvironment.setQualifiers("w${width}dp-h${height}dp-mdpi")
            RuntimeEnvironment.setFontScale(fontScale)
            val controller = Robolectric.buildActivity(Activity::class.java)
            val activity = controller.get()
            activity.setTheme(R.style.Theme_Sugarglider)
            controller.setup().visible()
            assertTrue(ApplicationLanguage.select(activity, language))
            var policyOpens = 0
            val dialog = PrivacyDetailsDialog.show(activity) { policyOpens++ }
            try {
                shadowOf(Looper.getMainLooper()).idle()
                val decor = dialog.window!!.decorView
                // Leave room for status/navigation insets and the dialog margins.
                decor.measure(View.MeasureSpec.makeMeasureSpec(width - 32, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(height - 80, View.MeasureSpec.AT_MOST))
                decor.layout(0, 0, decor.measuredWidth, decor.measuredHeight)
                assertTrue(decor.height <= height - 80)
                val message = decor.findViewWithTag<TextView>("privacy-description")
                assertEquals(ApplicationLanguage.text(activity, R.string.privacy_description), message.text.toString())
                val scroll = decor.findViewWithTag<ScrollView>("privacy-scroll")
                assertTrue("Disclosure retains readable scroll space", scroll.height >= 48)
                assertTrue("Full disclosure can scroll", message.height > scroll.height)
                scroll.scrollTo(0, message.height)
                assertTrue("Last disclosure paragraph is reachable",
                    scroll.scrollY + scroll.height >= message.bottom)
                assertEquals(ApplicationLanguage.text(activity, R.string.privacy_online),
                    decor.findViewWithTag<Button>("privacy-policy").text.toString())
                for (tag in listOf("privacy-close", "privacy-policy")) {
                    val button = decor.findViewWithTag<Button>(tag)
                    val visible = Rect()
                    assertTrue("$language $fontScale $width: action visible", button.getGlobalVisibleRect(visible))
                    assertEquals("$language $fontScale $width: action height", button.height, visible.height())
                    assertEquals("$language $fontScale $width: action width", button.width, visible.width())
                    assertTrue("Action retains its touch target", button.height >= 48)
                    val layout = button.layout
                    assertNotNull(layout)
                    assertTrue("$language $fontScale $width: text fits height",
                        layout.height <= button.height - button.compoundPaddingTop - button.compoundPaddingBottom)
                    for (line in 0 until layout.lineCount) {
                        assertEquals("Action text must not ellipsize", 0, layout.getEllipsisCount(line))
                        assertTrue("$language $fontScale $width: text fits width",
                            layout.getLineWidth(line) <= layout.width + 1)
                    }
                    assertEquals("Action text must remain complete", button.text.length,
                        layout.getLineEnd(layout.lineCount - 1))
                }
                assertEquals(0, policyOpens)
                decor.findViewWithTag<Button>("privacy-policy").performClick()
                assertEquals(1, policyOpens)
                assertFalse(dialog.isShowing)
            } finally {
                dialog.dismiss()
                controller.pause().stop().destroy()
            }
        }
    }
}
