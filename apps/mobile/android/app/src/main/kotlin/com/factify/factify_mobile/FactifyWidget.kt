package com.factify.factify_mobile

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews

/**
 * The home-screen widget (v5, 2.8): "Check copied text", "Photo" and "History".
 *
 * Each button opens the app where that starts - Check with the copied text pasted
 * in, the camera, or History - through the same channel shares arrive on
 * (MainActivity, ACTION_WIDGET). Written directly rather than with a widget
 * package: it is three buttons that open the app, and holds no data of its own.
 *
 * The widget never reads the clipboard itself. Only the tap on "Check copied text"
 * does, in the app, once the person has asked for it.
 */
class FactifyWidget : AppWidgetProvider() {

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val views = RemoteViews(context.packageName, R.layout.factify_widget).apply {
            setOnClickPendingIntent(R.id.widget_paste, open(context, "paste", 1))
            setOnClickPendingIntent(R.id.widget_camera, open(context, "camera", 2))
            setOnClickPendingIntent(R.id.widget_history, open(context, "history", 3))
        }
        for (id in ids) manager.updateAppWidget(id, views)
    }

    private fun open(context: Context, button: String, code: Int): PendingIntent =
        PendingIntent.getActivity(
            context,
            code,
            Intent(context, MainActivity::class.java).apply {
                action = MainActivity.ACTION_WIDGET
                putExtra(MainActivity.EXTRA_WIDGET, button)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
}
