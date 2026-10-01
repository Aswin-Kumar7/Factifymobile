package com.factify.factify_mobile

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileOutputStream

/**
 * Share-target intake, implemented directly rather than through a plugin.
 *
 * `receive_sharing_intent` (1.8.1 and 1.9.0) fails to configure: its
 * `android/build.gradle` calls `kotlin { ... }` without ever applying the Kotlin
 * Gradle plugin, so evaluating it aborts the whole build. Share intake is this
 * app's primary path — the content people need checked arrives in a forward, not
 * typed into a box — so it is not something to leave depending on an unmaintained
 * package that is currently broken.
 *
 * This is about a hundred lines, has no dependency, and does exactly what it says.
 *
 * Two intents matter. Note the mime types are written without a trailing
 * wildcard below because Kotlin block comments NEST, unlike Java's — a literal
 * slash-star inside this comment opens a level that never closes, and the whole
 * file then fails to parse with 'unclosed comment' pointing at the last line.
 *
 *   * ACTION_SEND with a text mime type — a forwarded message or a link.
 *   * ACTION_SEND with an image, video or application/pdf type — a forwarded file,
 *     delivered as a content:// URI that is readable only while this task holds
 *     the grant, which is why it is copied into cache immediately.
 */
class MainActivity : FlutterActivity() {

    private var channel: MethodChannel? = null

    /**
     * Held until Dart asks for it.
     *
     * A share that launches the app arrives before the Flutter engine is ready,
     * so delivering it eagerly would drop it. Dart calls `getInitialShare` once
     * it is listening; anything arriving later comes through `onNewIntent`.
     */
    private var pendingShare: Map<String, String?>? = null

    /**
     * Sign-in links: Google sign-in finishes in the browser, and the Factify server sends the
     * person back to factify://auth-callback with their session in the link. Held
     * like a share until Dart asks, for the same reason.
     */
    private var authChannel: MethodChannel? = null
    private var pendingAuthLink: String? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).apply {
            setMethodCallHandler { call, result ->
                when (call.method) {
                    "getInitialShare" -> {
                        result.success(pendingShare)
                        // Consumed, so returning to the app later does not
                        // re-verify the same content.
                        pendingShare = null
                    }
                    else -> result.notImplemented()
                }
            }
        }

        authChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, AUTH_CHANNEL).apply {
            setMethodCallHandler { call, result ->
                when (call.method) {
                    "getInitialAuthLink" -> {
                        result.success(pendingAuthLink)
                        pendingAuthLink = null
                    }
                    else -> result.notImplemented()
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pendingShare = parse(intent)
        pendingAuthLink = authLink(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)

        authLink(intent)?.let { link ->
            if (authChannel != null) authChannel?.invokeMethod("onAuthLink", link) else pendingAuthLink = link
            return
        }

        val share = parse(intent) ?: return
        // The engine is already running here, so push rather than park it.
        if (channel != null) channel?.invokeMethod("onShare", share) else pendingShare = share
    }

    /**
     * Turn a share intent into something Dart can act on, or null if it is not
     * a share at all (a normal launch, for instance).
     */
    private fun parse(intent: Intent?): Map<String, String?>? {
        if (intent == null) return null
        // Not shares, but delivered the same way: open a kept result (from the quick
        // verdict), or one of the home-screen widget's buttons.
        when (intent.action) {
            ACTION_OPEN_RECORD -> {
                val record = intent.getStringExtra(EXTRA_RECORD) ?: return null
                return mapOf("kind" to "record", "value" to record)
            }
            ACTION_WIDGET -> {
                val button = intent.getStringExtra(EXTRA_WIDGET) ?: return null
                return mapOf("kind" to "widget", "value" to button)
            }
        }
        if (intent.action != Intent.ACTION_SEND && intent.action != Intent.ACTION_SEND_MULTIPLE) {
            return null
        }

        val type = intent.type.orEmpty()

        if (type.startsWith("text/")) {
            val text = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()
            if (text.isNullOrEmpty()) return null
            // A URL and a block of prose go to different endpoints, and the
            // server decides which; the kind is reported, not guessed at here.
            val kind = if (text.startsWith("http://") || text.startsWith("https://")) "url" else "text"
            return mapOf("kind" to kind, "value" to text)
        }

        val uri: Uri? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
                ?: intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)?.firstOrNull()
        } else {
            @Suppress("DEPRECATION")
            (intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
                ?: intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)?.firstOrNull())
        }

        if (uri == null) return null

        // A file share that cannot be copied is reported, not dropped. Returning
        // null here used to make the share vanish: the app did nothing visible and
        // the result already on screen was lost with no explanation.
        val path = copyIntoCache(uri)
            ?: return mapOf(
                "kind" to "error",
                "value" to "That file could not be opened. Share it again, or use the Gallery button in Factify.",
                "mimeType" to type,
            )
        return mapOf("kind" to "file", "value" to path, "mimeType" to type)
    }

    /**
     * Copy the shared file into our own cache and return that path.
     *
     * The URI permission is scoped to this task and is revoked when it ends, so
     * handing the raw content:// URI to Dart yields a path that stops working at
     * an unpredictable moment. Copying costs one file write and makes the input
     * ours for as long as we need it.
     *
     * Cache, not files: this is transient input, and the OS may reclaim it. Raw
     * media is not something this product retains.
     */
    private fun copyIntoCache(uri: Uri): String? = try {
        val name = "share-${System.currentTimeMillis()}-${uri.lastPathSegment?.takeLast(40) ?: "item"}"
        val target = File(cacheDir, name.replace(Regex("[^A-Za-z0-9._-]"), "_"))

        contentResolver.openInputStream(uri)?.use { input ->
            FileOutputStream(target).use { output -> input.copyTo(output) }
        }

        if (target.length() > 0) target.absolutePath else null
    } catch (error: Exception) {
        // A share we cannot read must not crash the launch, and must not vanish
        // either: `parse` turns this null into an error share the person can see.
        null
    }

    /** The sign-in link this intent carries, or null. Only factify://auth-callback. */
    private fun authLink(intent: Intent?): String? {
        val data = intent?.data ?: return null
        if (intent.action != Intent.ACTION_VIEW) return null
        if (data.scheme != "factify" || data.host != "auth-callback") return null
        return data.toString()
    }

    companion object {
        private const val AUTH_CHANNEL = "factify/auth"
        private const val CHANNEL = "factify/share"

        /** Open a result kept in History: [EXTRA_RECORD] names it. */
        const val ACTION_OPEN_RECORD = "com.factify.factify_mobile.OPEN_RECORD"
        const val EXTRA_RECORD = "record"

        /** A home-screen widget button: [EXTRA_WIDGET] is paste, camera or history. */
        const val ACTION_WIDGET = "com.factify.factify_mobile.WIDGET"
        const val EXTRA_WIDGET = "button"
    }
}
