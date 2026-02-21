package com.yourcompany.toast;

import android.app.Activity;
import android.widget.Toast;

import com.unity3d.player.UnityPlayer;

public class ToastPlugin {

    public static void showToast(final String message, final boolean isLong) {
        final Activity activity = UnityPlayer.currentActivity;

        if (activity == null) return;

        activity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                Toast.makeText(
                        activity,
                        message,
                        isLong ? Toast.LENGTH_LONG : Toast.LENGTH_SHORT
                ).show();
            }
        });
    }
}
