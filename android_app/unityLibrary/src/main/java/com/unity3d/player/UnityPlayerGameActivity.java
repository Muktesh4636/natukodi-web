package com.unity3d.player;

import android.annotation.TargetApi;
import android.content.Intent;
import android.content.res.Configuration;
import android.os.Build;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.SurfaceView;
import android.widget.FrameLayout;

import androidx.core.view.ViewCompat;
import com.unity3d.player.UnityPlayer;
import org.json.JSONObject;
import android.util.Log;

import com.google.androidgamesdk.GameActivity;

public class UnityPlayerGameActivity extends GameActivity
        implements IUnityPlayerLifecycleEvents, IUnityPermissionRequestSupport, IUnityPlayerSupport {
    class GameActivitySurfaceView extends InputEnabledSurfaceView {
        GameActivity mGameActivity;

        public GameActivitySurfaceView(GameActivity activity) {
            super(activity);
            mGameActivity = activity;
        }

        // Reroute motion events from captured pointer to normal events
        // Otherwise when doing Cursor.lockState = CursorLockMode.Locked from C# the
        // touch and mouse events will stop working
        @Override
        public boolean onCapturedPointerEvent(MotionEvent event) {
            return mGameActivity.onTouchEvent(event);
        }
    }

    protected UnityPlayerForGameActivity mUnityPlayer;

    protected String updateUnityCommandLineArguments(String cmdLine) {
        return cmdLine;
    }

    static {
        System.loadLibrary("game");
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
    }

    @Override
    public UnityPlayerForGameActivity getUnityPlayerConnection() {
        return mUnityPlayer;
    }

    // Soft keyboard relies on inset listener for listening to various events -
    // keyboard opened/closed/text entered.
    private void applyInsetListener(SurfaceView surfaceView) {
        surfaceView.getViewTreeObserver().addOnGlobalLayoutListener(
                () -> onApplyWindowInsets(surfaceView, ViewCompat.getRootWindowInsets(getWindow().getDecorView())));
    }

    @Override
    protected InputEnabledSurfaceView createSurfaceView() {
        return new GameActivitySurfaceView(this);
    }

    @Override
    protected void onCreateSurfaceView() {
        super.onCreateSurfaceView();
        FrameLayout frameLayout = findViewById(contentViewId);

        applyInsetListener(mSurfaceView);

        mSurfaceView.setId(UnityPlayerForGameActivity.getUnityViewIdentifier(this));

        String cmdLine = updateUnityCommandLineArguments(getIntent().getStringExtra("unity"));
        getIntent().putExtra("unity", cmdLine);
        // Unity requires access to frame layout for setting the static splash screen.
        // Note: we cannot initialize in onCreate (after super.onCreate), because game
        // activity native thread would be already started and unity runtime initialized
        // we also cannot initialize before super.onCreate since frameLayout is not yet
        // available.
        mUnityPlayer = new UnityPlayerForGameActivity(this, frameLayout, mSurfaceView, this);
    }

    @Override
    public void onUnityPlayerUnloaded() {

    }

    @Override
    public void onUnityPlayerQuitted() {
        finish();
    }

    // Quit Unity
    @Override
    protected void onDestroy() {
        mUnityPlayer.destroy();
        super.onDestroy();
    }

    @Override
    protected void onStop() {
        // Note: we want Java onStop callbacks to be processed before the native part
        // processes the onStop callback
        mUnityPlayer.onStop();
        super.onStop();
    }

    @Override
    protected void onStart() {
        // Note: we want Java onStart callbacks to be processed before the native part
        // processes the onStart callback
        mUnityPlayer.onStart();
        super.onStart();
    }

    // Pause Unity
    @Override
    protected void onPause() {
        // Note: we want Java onPause callbacks to be processed before the native part
        // processes the onPause callback
        mUnityPlayer.onPause();
        super.onPause();
    }

    // Resume Unity
    @Override
    protected void onResume() {
        // Note: we want Java onResume callbacks to be processed before the native part
        // processes the onResume callback
        mUnityPlayer.onResume();
        super.onResume();
        sendLoginDataToUnity();
        addProfileOverlay();
        addBalanceOverlay();
    }

    // Configuration changes are used by Video playback logic in Unity
    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        mUnityPlayer.configurationChanged(newConfig);
        super.onConfigurationChanged(newConfig);
    }

    // Notify Unity of the focus change.
    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        mUnityPlayer.windowFocusChanged(hasFocus);
        super.onWindowFocusChanged(hasFocus);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        // To support deep linking, we need to make sure that the client can get access
        // to
        // the last sent intent. The clients access this through a JNI api that allows
        // them
        // to get the intent set on launch. To update that after launch we have to
        // manually
        // replace the intent with the one caught here.
        setIntent(intent);
        mUnityPlayer.newIntent(intent);
    }

    @Override
    @TargetApi(Build.VERSION_CODES.M)
    public void requestPermissions(PermissionRequest request) {
        mUnityPlayer.addPermissionRequest(request);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        mUnityPlayer.permissionResponse(this, requestCode, permissions, grantResults);
    }

    @Override
    public void onBackPressed() {
        finish();
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getKeyCode() == KeyEvent.KEYCODE_BACK && event.getAction() == KeyEvent.ACTION_UP) {
            finish();
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    private void sendLoginDataToUnity() {
        // Fetch LIVE data from SharedPreferences (SessionManager)
        // This ensures that even if tokens rotate, Unity gets the latest versions
        android.content.SharedPreferences appPrefs = getSharedPreferences("gunduata_prefs",
                android.content.Context.MODE_PRIVATE);
        String _token = appPrefs.getString("auth_token", null);
        String _refreshToken = appPrefs.getString("refresh_token", null);
        String _username = appPrefs.getString("username", null);
        String _password = appPrefs.getString("user_pass", null);
        String _userId = null;

        // Safely get user_id which might be stored as Int by SessionManager
        if (appPrefs.contains("user_id")) {
            Object userIdObj = appPrefs.getAll().get("user_id");
            if (userIdObj != null) {
                _userId = String.valueOf(userIdObj);
            }
        }

        // Fallback to Intent if Prefs are empty
        Intent intent = getIntent();
        if (_token == null && intent != null) {
            _token = intent.getStringExtra("token");
            _refreshToken = intent.getStringExtra("refresh_token");
            _username = intent.getStringExtra("username");
            _userId = intent.getStringExtra("user_id");
            _password = intent.getStringExtra("password");
        }

        final String token = _token;
        final String refreshToken = _refreshToken;
        final String username = _username;
        final String userId = _userId;
        final String password = _password;

        if (token != null && !token.isEmpty()) {
            // Persistent Autologin: Write directly to SharedPreferences (Unity PlayerPrefs)
            // This ensures the game sees the user as logged in PRE-INITIALIZATION
            saveToPlayerPrefs(username, password, token);

            try {
                JSONObject json = new JSONObject();
                json.put("access", token);
                json.put("token", token);
                json.put("accessToken", token);
                json.put("refresh", refreshToken);
                json.put("refreshToken", refreshToken);
                json.put("username", username);
                json.put("user_id", userId);
                json.put("password", password);
                final String jsonString = json.toString();

                Log.d("UnityLoginBypass",
                        "Preparing EXHAUSTIVE SHOTGUN injection for: " + username + " (ID: " + userId + ")");

                android.os.Handler handler = new android.os.Handler(android.os.Looper.getMainLooper());
                // Prolonged injection: every 500ms for 15 seconds to ensure we hit the right
                // moment
                for (int i = 0; i < 30; i++) {
                    final int attempt = i;
                    final long currentDelay = i * 500L;
                    handler.postDelayed(new Runnable() {
                        @Override
                        public void run() {
                            if (attempt % 10 == 0) {
                                Log.d("UnityLoginBypass", "Shotgun injection batch: " + (attempt * 500) + "ms");
                            }

                            // --- TARGET ALL RELEVANT OBJECTS DISCOVERED IN METADATA ---
                            // Target: GameManager
                            UnityPlayer.UnitySendMessage("GameManager", "SetAccessAndRefreshTokens", jsonString);
                            UnityPlayer.UnitySendMessage("GameManager", "Login", jsonString);
                            UnityPlayer.UnitySendMessage("GameManager", "SetToken", token);
                            UnityPlayer.UnitySendMessage("GameManager", "ReceiveToken", token);

                            // Target: LoginUIManager
                            UnityPlayer.UnitySendMessage("LoginUIManager", "SetAccessAndRefreshTokens", jsonString);
                            UnityPlayer.UnitySendMessage("LoginUIManager", "LoginUser", username);
                            UnityPlayer.UnitySendMessage("LoginUIManager", "OnLoginSuccess", jsonString);
                            UnityPlayer.UnitySendMessage("LoginUIManager", "AutoLoginIfPossible", "");

                            // Target: UIManager
                            UnityPlayer.UnitySendMessage("UIManager", "ShowPanel", "3");
                            UnityPlayer.UnitySendMessage("UIManager", "ShowPanel", "Gameplay");
                            UnityPlayer.UnitySendMessage("UIManager", "AutoLoginIfPossible", "");
                            UnityPlayer.UnitySendMessage("UIManager", "SetAccessAndRefreshTokens", jsonString);
                            UnityPlayer.UnitySendMessage("UIManager", "OnLoginSuccess", jsonString);

                            // --- Fallbacks ---
                            UnityPlayer.UnitySendMessage("Bridge", "SetToken", token);
                            UnityPlayer.UnitySendMessage("GameplayUIManager", "SetAccessAndRefreshTokens",
                                    jsonString);
                        }
                    }, currentDelay);
                }

            } catch (Exception e) {
                Log.e("UnityLoginBypass", "Error setting up login data injection", e);
            }
        }
    }

    private void saveToPlayerPrefs(String username, String password, String token) {
        try {
            // Unity stores PlayerPrefs in SharedPreferences with name:
            // [package_name].v2.playerprefs
            String prefsName = getPackageName() + ".v2.playerprefs";
            android.content.SharedPreferences prefs = getSharedPreferences(prefsName,
                    android.content.Context.MODE_PRIVATE);
            android.content.SharedPreferences.Editor editor = prefs.edit();

            // Internal Unity PlayerPrefs format for strings (sometimes needs type prefix,
            // but usually standard works)
            editor.putString("username", username);
            editor.putString("password", password);
            editor.putString("token", token);

            // Redundant keys for common variants
            editor.putString("USERNAME_KEY", username);
            editor.putString("PASSWORD_KEY", password);
            editor.putString("access_token", token);

            editor.apply();
            Log.d("UnityLoginBypass", "Successfully wrote credentials to persistent PlayerPrefs (" + prefsName + ")");
        } catch (Exception e) {
            Log.e("UnityLoginBypass", "Failed to write to PlayerPrefs", e);
        }
    }

    private void addProfileOverlay() {
        android.view.View overlay = new android.view.View(this);
        int width = getResources().getDisplayMetrics().widthPixels;
        int height = getResources().getDisplayMetrics().heightPixels;

        // Based on screenshot analysis, the profile icon is roughly in top-left
        android.widget.FrameLayout.LayoutParams params = new android.widget.FrameLayout.LayoutParams(
                (int) (width * 0.20),
                (int) (height * 0.12));
        params.gravity = android.view.Gravity.TOP | android.view.Gravity.START;

        overlay.setLayoutParams(params);
        overlay.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View v) {
                android.util.Log.d("UnityNavigation", "Profile overlay clicked, returning to dashboard");
                finish();
            }
        });

        android.widget.FrameLayout container = findViewById(contentViewId);
        if (container != null) {
            container.addView(overlay);
        }
    }

    private void addBalanceOverlay() {
        android.view.View overlay = new android.view.View(this);
        int width = getResources().getDisplayMetrics().widthPixels;
        int height = getResources().getDisplayMetrics().heightPixels;

        // Balance is roughly in top-right
        android.widget.FrameLayout.LayoutParams params = new android.widget.FrameLayout.LayoutParams(
                (int) (width * 0.25),
                (int) (height * 0.12));
        params.gravity = android.view.Gravity.TOP | android.view.Gravity.END;

        overlay.setLayoutParams(params);
        overlay.setOnClickListener(new android.view.View.OnClickListener() {
            @Override
            public void onClick(android.view.View v) {
                Log.d("UnityNavigation", "Balance overlay clicked, redirecting to deposit");
                try {
                    Class<?> mainActivityClass = Class.forName("com.sikwin.app.MainActivity");
                    Intent redirectIntent = new Intent(UnityPlayerGameActivity.this, mainActivityClass);
                    redirectIntent.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
                    redirectIntent.putExtra("redirect", "deposit");
                    startActivity(redirectIntent);
                    finish();
                } catch (ClassNotFoundException e) {
                    Log.e("UnityNavigation", "Could not find MainActivity class", e);
                    finish();
                }
            }
        });

        android.widget.FrameLayout container = findViewById(contentViewId);
        if (container != null) {
            container.addView(overlay);
        }
    }
}
