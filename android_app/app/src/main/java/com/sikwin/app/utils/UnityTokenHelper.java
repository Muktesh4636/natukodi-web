package com.sikwin.app.utils;

import android.content.Context;
import android.content.Intent;
import android.util.Log;
import org.json.JSONObject;

public class UnityTokenHelper {
    
    /**
     * Send authentication tokens to Unity using Broadcast
     * This works even across different processes (:unity process)
     */
    public static void sendTokensToUnity(Context context, String access, String refresh, String username) {
        try {
            Log.d("UnityTokenHelper", "Sending tokens to Unity via Broadcast");
            
            Intent intent = new Intent("com.sikwin.app.TOKEN_UPDATE");
            intent.putExtra("access", access);
            intent.putExtra("refresh", refresh);
            intent.putExtra("username", username != null ? username : "");
            
            // Ensure the broadcast reaches the :unity process
            intent.setPackage(context.getPackageName());
            context.sendBroadcast(intent);
            
            Log.d("UnityTokenHelper", "Token broadcast sent successfully");
        } catch (Exception e) {
            Log.e("UnityTokenHelper", "Error sending token broadcast: " + e.getMessage());
        }
    }

    /**
     * Trigger logout in Unity using Broadcast
     */
    public static void sendLogoutToUnity(Context context) {
        try {
            Log.d("UnityTokenHelper", "Sending logout to Unity via Broadcast");
            Intent intent = new Intent("com.sikwin.app.TOKEN_UPDATE");
            intent.putExtra("action", "logout");
            intent.setPackage(context.getPackageName());
            context.sendBroadcast(intent);
        } catch (Exception e) {
            Log.e("UnityTokenHelper", "Error sending logout broadcast: " + e.getMessage());
        }
    }
}
