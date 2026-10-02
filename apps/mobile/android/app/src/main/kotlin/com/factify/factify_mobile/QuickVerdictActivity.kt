package com.factify.factify_mobile

import android.content.ClipboardManager
import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterActivityLaunchConfigs.BackgroundMode
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.MethodChannel.Result

/**
 * The quick verdict over the chat (v5, 2.7).
 *
 * Text shared to Factify opens here: a see-through window over the chat it came
 * from, with the answer in a sheet at the bottom, so the person can copy a
 * correction and paste it straight back without leaving the conversation. The
 * Dart side is its own small entry point (`quickVerdictMain` in lib/main.dart),
 * not the whole app.
 *
 * Only text and links come here. Pictures, videos and PDFs still open the full
 * app (MainActivity), which has the room to show what was checked in them. And
 * when the person has turned the quick verdict off in Profile, the Dart side hands
 * the text straight on to the full app (`openFullApp`) and this window closes.
 *
 * The floating button (FactifyBubbleService) opens it too, with ACTION_FROM_BUBBLE:
 * then the text is whatever was just copied. Android lets an app read the clipboard
 * only while its window has focus, so Dart's request for the text waits until it
 * does (`onWindowFocusChanged`).
 */
class QuickVerdictActivity : FlutterActivity() {

    /** The shared text, held until Dart asks for it (it arrives before Dart runs). */
    private var shared: Map<String, String>? = null

    /** Opened by the floating button: the text is on the clipboard. */
    private var fromBubble = false

    /** Dart's request for the copied text, answered once this window has focus. */
    private var waiting: Result? = null

    override fun getDartEntrypointFunctionName(): String = "quickVerdictMain"

    /** See-through, so the chat stays visible behind the sheet. */
    override fun getBackgroundMode(): BackgroundMode = BackgroundMode.transparent

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        fromBubble = intent?.action == ACTION_FROM_BUBBLE
        shared = parse(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.action == ACTION_FROM_BUBBLE) {
            // The button tapped again with this window open: start over with what is
            // copied now, rather than leave the earlier answer showing.
            recreate()
            return
        }
        shared = parse(intent)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) waiting?.let { answerFromClipboard(it) }
    }

    /** The copied text, or a word to copy something first and this window closed. */
    private fun answerFromClipboard(result: Result) {
        waiting = null
        fromBubble = false
        val clipboard = getSystemService(ClipboardManager::class.java)
        val text = clipboard?.primaryClip
            ?.takeIf { it.itemCount > 0 }
            ?.getItemAt(0)
            ?.coerceToText(this)
            ?.toString()
            ?.trim()
        if (text.isNullOrEmpty()) {
            Toast.makeText(this, R.string.bubble_nothing_copied, Toast.LENGTH_LONG).show()
            result.success(null)
            return
        }
        val kind = if (text.startsWith("http://") || text.startsWith("https://")) "url" else "text"
        result.success(mapOf("kind" to kind, "value" to text))
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "getShare" -> {
                    if (shared == null && fromBubble) {
                        if (hasWindowFocus()) answerFromClipboard(result) else waiting = result
                    } else {
                        result.success(shared)
                        shared = null
                    }
                }
                // The full app, with the text shared into it: the quick verdict is
                // off, or the person needs to sign in first.
                "openFullApp" -> {
                    val text = call.argument<String>("text")
                    startActivity(
                        Intent(this, MainActivity::class.java).apply {
                            action = Intent.ACTION_SEND
                            type = "text/plain"
                            putExtra(Intent.EXTRA_TEXT, text)
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        },
                    )
                    result.success(null)
                    finish()
                }
                // The full result, from History, where the finished check was kept.
                "openResult" -> {
                    startActivity(
                        Intent(this, MainActivity::class.java).apply {
                            action = MainActivity.ACTION_OPEN_RECORD
                            putExtra(MainActivity.EXTRA_RECORD, call.argument<String>("record"))
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        },
                    )
                    result.success(null)
                    finish()
                }
                "close" -> {
                    result.success(null)
                    finish()
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun parse(intent: Intent?): Map<String, String>? {
        if (intent?.action != Intent.ACTION_SEND) return null
        val text = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()
        if (text.isNullOrEmpty()) return null
        val kind = if (text.startsWith("http://") || text.startsWith("https://")) "url" else "text"
        return mapOf("kind" to kind, "value" to text)
    }

    companion object {
        const val ACTION_FROM_BUBBLE = "com.factify.factify_mobile.FROM_BUBBLE"
        private const val CHANNEL = "factify/quick"
    }
}
