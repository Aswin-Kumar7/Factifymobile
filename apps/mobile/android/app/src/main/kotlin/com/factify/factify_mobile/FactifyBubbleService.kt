package com.factify.factify_mobile

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import kotlin.math.abs

/**
 * The floating Factify button, over every app.
 *
 * WhatsApp gives a text message no Share button, so "share it to Factify" never
 * reached the most common forward. The button is how it does now, the way Google
 * Translate's Tap to Translate works: copy the message, tap the button, and the
 * quick verdict opens over the chat.
 *
 * The button cannot read the clipboard itself - since Android 10 only the app in
 * front (or the keyboard) may. So a tap opens QuickVerdictActivity, the see-through
 * window, which reads it once it has focus (ACTION_FROM_BUBBLE).
 *
 * Drawn with "display over other apps" (SYSTEM_ALERT_WINDOW), which the person grants
 * once in Settings; kept alive by a quiet foreground notification, whose "Turn off"
 * stops it. Drag to move; it settles against the nearer edge.
 */
class FactifyBubbleService : Service() {

    private var windowManager: WindowManager? = null
    private var bubble: View? = null
    private var params: WindowManager.LayoutParams? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP || !Settings.canDrawOverlays(this)) {
            stopSelf()
            return START_NOT_STICKY
        }
        showNotice()
        if (bubble == null) addBubble()
        running = true
        return START_STICKY
    }

    override fun onDestroy() {
        bubble?.let { windowManager?.removeView(it) }
        bubble = null
        running = false
        super.onDestroy()
    }

    private fun showNotice() {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, getString(R.string.bubble_channel), NotificationManager.IMPORTANCE_MIN),
            )
        }
        val stop = PendingIntent.getService(
            this,
            0,
            Intent(this, FactifyBubbleService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        val notice = builder
            .setSmallIcon(R.drawable.widget_mark)
            .setContentTitle(getString(R.string.bubble_on))
            .setContentText(getString(R.string.bubble_how))
            .setOngoing(true)
            .addAction(Notification.Action.Builder(null, getString(R.string.bubble_turn_off), stop).build())
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTICE_ID, notice, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTICE_ID, notice)
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun addBubble() {
        val manager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val density = resources.displayMetrics.density
        val size = (56 * density).toInt()

        val view = FrameLayout(this).apply {
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(0xFFFFFFFF.toInt())
            }
            elevation = 6 * density
            contentDescription = getString(R.string.bubble_label)
            val pad = (6 * density).toInt()
            setPadding(pad, pad, pad, pad)
            addView(
                ImageView(context).apply {
                    setImageResource(R.drawable.widget_seal)
                    scaleType = ImageView.ScaleType.FIT_CENTER
                },
                FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT),
            )
        }

        @Suppress("DEPRECATION")
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            WindowManager.LayoutParams.TYPE_PHONE
        }
        val layout = WindowManager.LayoutParams(
            size,
            size,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = resources.displayMetrics.widthPixels - size
            y = (resources.displayMetrics.heightPixels * 0.35).toInt()
        }

        val slop = ViewConfiguration.get(this).scaledTouchSlop
        var startX = 0
        var startY = 0
        var downX = 0f
        var downY = 0f
        var moved = false
        view.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    startX = layout.x
                    startY = layout.y
                    downX = event.rawX
                    downY = event.rawY
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - downX
                    val dy = event.rawY - downY
                    if (abs(dx) > slop || abs(dy) > slop) moved = true
                    if (moved) {
                        layout.x = startX + dx.toInt()
                        layout.y = startY + dy.toInt()
                        manager.updateViewLayout(view, layout)
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (moved) settle(manager, view, layout, size) else openQuickVerdict()
                    true
                }
                else -> false
            }
        }

        manager.addView(view, layout)
        windowManager = manager
        bubble = view
        params = layout
    }

    /** Against the nearer side, and back on screen if it was dragged off. */
    private fun settle(manager: WindowManager, view: View, layout: WindowManager.LayoutParams, size: Int) {
        val width = resources.displayMetrics.widthPixels
        val height = resources.displayMetrics.heightPixels
        layout.x = if (layout.x + size / 2 < width / 2) 0 else width - size
        layout.y = layout.y.coerceIn(0, height - size * 2)
        manager.updateViewLayout(view, layout)
    }

    private fun openQuickVerdict() {
        startActivity(
            Intent(this, QuickVerdictActivity::class.java).apply {
                action = QuickVerdictActivity.ACTION_FROM_BUBBLE
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            },
        )
    }

    companion object {
        const val ACTION_STOP = "com.factify.factify_mobile.BUBBLE_STOP"
        private const val CHANNEL = "factify_bubble"
        private const val NOTICE_ID = 4107

        /** Whether the button is showing, for Profile's switch. */
        @Volatile
        var running = false
            private set

        fun start(context: Context) {
            val intent = Intent(context, FactifyBubbleService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, FactifyBubbleService::class.java))
        }
    }
}
