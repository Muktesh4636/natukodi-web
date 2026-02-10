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
            String jsonString = json.toString();
            
            Log.d("UnityTokenHelper", "Sending tokens to Unity: GameManager");
            
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
            unitySendMessage.invoke(null, "GameManager", "Login", jsonString);
            
            // Send to LoginUIManager if it exists
            unitySendMessage.invoke(null, "LoginUIManager", "SetAccessAndRefreshTokens", jsonString);
            
            // Send to UIManager if it exists
            unitySendMessage.invoke(null, "UIManager", "SetAccessAndRefreshTokens", jsonString);
            
            Log.d("UnityTokenHelper", "Tokens sent successfully to Unity");
        } catch (ClassNotFoundException e) {
            // Unity library not available, tokens will be sent when Unity starts via Intent/PlayerPrefs
            Log.d("UnityTokenHelper", "UnityPlayer not available yet, tokens will be sent when Unity starts");
        } catch (Exception e) {
            Log.e("UnityTokenHelper", "Error sending tokens to Unity: " + e.getMessage(), e);
        }
    }
}
