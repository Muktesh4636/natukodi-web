package com.unity3d.player;

/**
 * Static holder for auth tokens - reliable bridge when Intent/SharedPreferences
 * fail. Kotlin sets before launching Unity; UnityPlayerGameActivity reads here.
 */
public class UnityTokenHolder {
    private static volatile String accessToken;
    private static volatile String refreshToken;
    private static volatile String username;
    private static volatile String password;

    public static void setTokens(String access, String refresh, String user, String pass) {
        accessToken = access;
        refreshToken = refresh;
        username = user;
        password = pass;
    }

    public static String getAccessToken() {
        return accessToken;
    }

    public static String getRefreshToken() {
        return refreshToken;
    }

    public static String getUsername() {
        return username;
    }

    public static String getPassword() {
        return password;
    }

    public static void clear() {
        accessToken = null;
        refreshToken = null;
        username = null;
        password = null;
    }
}
