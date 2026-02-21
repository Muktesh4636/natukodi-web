package com.sikwin.app.utils;

import android.util.Log;
import org.json.JSONObject;

public class UnityTokenHelper {
    
    /**
     * Send authentication tokens to Unity GameManager using reflection
     * This should be called after successful login in Kotlin
     */
    public static void sendTokensToUnity(String access, String refresh, String username) {
        try {
            JSONObject json = new JSONObject();
            json.put("access", access);
            json.put("refresh", refresh);
            json.put("username", username != null ? username : "");
            final String jsonString = json.toString();
            
            Log.d("UnityTokenHelper", "Sending tokens to Unity: GameManager");
            
            // Run on UI thread to ensure UnityPlayer is accessible
            android.os.Handler handler = new android.os.Handler(android.os.Looper.getMainLooper());
            handler.post(new Runnable() {
                @Override
                public void run() {
                    try {
                        // Use reflection to access UnityPlayer since it's in a different module
                        Class<?> unityPlayerClass = Class.forName("com.unity3d.player.UnityPlayer");
                        java.lang.reflect.Method unitySendMessage = unityPlayerClass.getMethod(
                            "UnitySendMessage", 
                            String.class, 
                            String.class, 
                            String.class
                        );
                        
                        // Send to GameManager (primary target)
                        unitySendMessage.invoke(null, "GameManager", "SetAccessAndRefreshTokens", jsonString);
                        unitySendMessage.invoke(null, "GameManager", "SetToken", access);
                        
                        Log.d("UnityTokenHelper", "Tokens sent successfully to Unity via reflection");
                    } catch (ClassNotFoundException e) {
                        Log.d("UnityTokenHelper", "UnityPlayer not available yet");
                    } catch (Exception e) {
                        Log.e("UnityTokenHelper", "Error in UI thread sending tokens: " + e.getMessage());
                    }
                }
            });
        } catch (Exception e) {
            Log.e("UnityTokenHelper", "Error preparing tokens for Unity: " + e.getMessage(), e);
        }
    }

    /**
     * Trigger logout in Unity GameManager
     */
    public static void sendLogoutToUnity() {
        try {
            Log.d("UnityTokenHelper", "Sending logout to Unity: GameManager");
            
            android.os.Handler handler = new android.os.Handler(android.os.Looper.getMainLooper());
            handler.post(new Runnable() {
                @Override
                public void run() {
                    try {
                        Class<?> unityPlayerClass = Class.forName("com.unity3d.player.UnityPlayer");
                        java.lang.reflect.Method unitySendMessage = unityPlayerClass.getMethod(
                            "UnitySendMessage", 
                            String.class, 
                            String.class, 
                            String.class
                        );
                        
                        unitySendMessage.invoke(null, "GameManager", "Logout", "");
                        Log.d("UnityTokenHelper", "Logout signal sent successfully to Unity");
                    } catch (Exception e) {
                        Log.e("UnityTokenHelper", "Error sending logout to Unity: " + e.getMessage());
                    }
                }
            });
        } catch (Exception e) {
            Log.e("UnityTokenHelper", "Error preparing logout for Unity: " + e.getMessage());
        }
    }
}
