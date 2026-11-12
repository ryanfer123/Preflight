package dev.preflight.app.ui

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import com.google.android.material.button.MaterialButton

/** Small native view vocabulary: all document-derived text uses plain TextView content. */
class Widgets(val context: Context) {
    val ink = Color.rgb(23, 34, 59)
    val muted = Color.rgb(87, 98, 122)
    val indigo = Color.rgb(65, 69, 184)
    val ground = Color.rgb(244, 246, 251)
    val line = Color.rgb(220, 225, 236)
    fun dp(value: Int) = (value * context.resources.displayMetrics.density).toInt()
    fun column(padding: Int = 0): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL; setPadding(dp(padding), dp(padding), dp(padding), dp(padding))
    }
    fun text(value: String, size: Int = 15, color: Int = ink, bold: Boolean = false,
             heading: Boolean = false): TextView = TextView(context).apply {
        text = value; textSize = size.toFloat(); setTextColor(color)
        if (bold) typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        setLineSpacing(dp(3).toFloat(), 1f)
        if (heading) isAccessibilityHeading = true
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) }
    }
    fun button(label: String, enabled: Boolean = true, outlined: Boolean = false,
               action: () -> Unit): MaterialButton = MaterialButton(context, null,
        if (outlined) com.google.android.material.R.attr.materialButtonOutlinedStyle
        else com.google.android.material.R.attr.materialButtonStyle).apply {
        text = label; isAllCaps = false; textSize = 15f; minHeight = dp(54); cornerRadius = dp(13)
        isEnabled = enabled
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6); bottomMargin = dp(6) }
        setOnClickListener { action() }
    }
    fun card(color: Int = Color.WHITE): LinearLayout = column(20).apply {
        background = shape(color, 18, line)
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12); bottomMargin = dp(8) }
    }
    fun shape(color: Int, radius: Int, stroke: Int? = null) = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(radius).toFloat()
        if (stroke != null) setStroke(dp(1), stroke)
    }
    fun gap(height: Int = 12) = View(context).apply {
        layoutParams = LinearLayout.LayoutParams(1, dp(height))
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
    }
    fun badge(label: String): TextView = text(label, 12, indigo, true).apply {
        gravity = Gravity.CENTER; setPadding(dp(12), dp(6), dp(12), dp(6))
        background = shape(Color.rgb(237, 239, 255), 30)
        layoutParams = LinearLayout.LayoutParams(-2, -2).apply { bottomMargin = dp(12) }
    }
    fun status(verdict: String): Pair<Int, Int> = when (verdict) {
        "PASS" -> Color.rgb(231, 243, 238) to Color.rgb(23, 100, 77)
        "BLOCK" -> Color.rgb(251, 233, 236) to Color.rgb(166, 41, 57)
        else -> Color.rgb(255, 243, 217) to Color.rgb(128, 80, 0)
    }
}
