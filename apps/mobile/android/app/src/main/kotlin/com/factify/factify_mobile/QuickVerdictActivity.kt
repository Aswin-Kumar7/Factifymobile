package com.factify.factify_mobile

import android.content.Intent
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterActivityLaunchConfigs.BackgroundMode
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

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
 */
class QuickVerdictActivity : FlutterActivity() {

    /** The shared text, held until Dart asks for it (it arrives before Dart runs). */
    private var shared: Map<String, String>? = null

    override fun getDartEntrypointFunctionName(): String = "quickVerdictMain"

    /** See-through, so the chat stays visible behind the sheet. */
    override fun getBackgroundMode(): BackgroundMode = BackgroundMode.transparent

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        shared = parse(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        shared = parse(intent)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "getShare" -> {
                    result.success(shared)
                    shared = null
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

    private companion object {
        const val CHANNEL = "factify/quick"
    }
}
