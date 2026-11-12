package dev.preflight.app.ui

import android.content.Intent
import android.os.Bundle
import android.provider.OpenableColumns
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.ViewModelProvider
import dev.preflight.app.R
import com.google.android.material.bottomnavigation.BottomNavigationView

/** Native Android entry point. No browser wrapper and no client-side payment verdicts. */
class MainActivity : AppCompatActivity() {
    private lateinit var model: PreflightViewModel
    private lateinit var body: LinearLayout
    private lateinit var progress: ProgressBar
    private lateinit var navigation: BottomNavigationView
    private lateinit var screens: Screens
    private var pickingEmail = false
    private val picker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            runCatching { contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
            var filename = if (pickingEmail) "original.eml" else "invoice.pdf"
            var size: Long? = null
            contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (nameIndex >= 0) filename = cursor.getString(nameIndex) ?: filename
                    val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
                    if (sizeIndex >= 0 && !cursor.isNull(sizeIndex)) size = cursor.getLong(sizeIndex)
                }
            }
            if ((size ?: 0) > 10 * 1024 * 1024) model.showError("Each file must be at most 10 MiB.")
            else model.selectDocument(SelectedDocument(uri.toString(), filename), pickingEmail)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        model = ViewModelProvider(this)[PreflightViewModel::class.java]
        pickingEmail = savedInstanceState?.getBoolean("picking_email") ?: false
        val w = Widgets(this)
        val root = w.column().apply { setBackgroundColor(w.ground) }
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            val keyboard = insets.getInsets(WindowInsetsCompat.Type.ime())
            view.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, keyboard.bottom)); insets
        }
        val toolbar = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL; minimumHeight = w.dp(64)
            setPadding(w.dp(24), w.dp(12), w.dp(24), w.dp(12))
            setBackgroundColor(android.graphics.Color.WHITE)
        }
        toolbar.addView(w.text("p.", 30, android.graphics.Color.WHITE, true).apply {
            gravity = Gravity.CENTER; background = w.shape(w.indigo, 12)
            layoutParams = LinearLayout.LayoutParams(w.dp(40), w.dp(40)).apply { marginEnd = w.dp(12) }
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        })
        toolbar.addView(w.text("preflight", 23, bold = true).apply {
            layoutParams = LinearLayout.LayoutParams(-2, -2)
        })
        root.addView(toolbar)
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            isIndeterminate = true; contentDescription = "Request in progress"
        }
        root.addView(progress, LinearLayout.LayoutParams(-1, w.dp(3)))
        body = w.column(24).apply { id = R.id.screen_body }
        val scroll = ScrollView(this).apply { isFillViewport = true; addView(body) }
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        navigation = BottomNavigationView(this).apply {
            inflateMenu(R.menu.navigation)
            setBackgroundColor(android.graphics.Color.WHITE)
            labelVisibilityMode = com.google.android.material.navigation.NavigationBarView.LABEL_VISIBILITY_LABELED
            setOnItemSelectedListener { item ->
                val target = when (item.itemId) { R.id.nav_ledger -> Screen.LEDGER; R.id.nav_connection -> Screen.CONNECTION; else -> Screen.CHECK }
                if (model.state.value?.screen != target) model.navigate(target)
                true
            }
        }
        root.addView(navigation)
        setContentView(root)
        screens = Screens(w, model) { email ->
            pickingEmail = email
            picker.launch(if (email) arrayOf("message/rfc822", "application/octet-stream")
                else arrayOf("application/pdf", "image/png", "image/jpeg"))
        }
        var previousScreen: Screen? = null
        model.state.observe(this) { state ->
            progress.visibility = if (state.busy) View.VISIBLE else View.INVISIBLE
            for (index in 0 until navigation.menu.size()) navigation.menu.getItem(index).isEnabled = !state.busy
            val item = when (state.screen) {
                Screen.LEDGER, Screen.APPROVAL -> R.id.nav_ledger
                Screen.CONNECTION -> R.id.nav_connection
                else -> R.id.nav_check
            }
            // Set checked state directly: programmatic selection must not trigger navigation.
            navigation.menu.findItem(item).isChecked = true
            val savedScroll = if (previousScreen == state.screen) scroll.scrollY else 0
            body.removeAllViews(); screens.render(body, state)
            scroll.post { scroll.scrollTo(0, savedScroll) }
            previousScreen = state.screen
        }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (model.state.value?.busy == true) return
                when (model.state.value?.screen) {
                    Screen.APPROVAL -> model.navigate(Screen.LEDGER)
                    Screen.CHECK -> finish()
                    else -> model.navigate(Screen.CHECK)
                }
            }
        })
    }
    override fun onSaveInstanceState(outState: Bundle) {
        outState.putBoolean("picking_email", pickingEmail)
        super.onSaveInstanceState(outState)
    }
}
