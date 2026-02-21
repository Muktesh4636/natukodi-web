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
import org.json.JSONObject;
import android.util.Log;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.IntentFilter;

import com.google.androidgamesdk.GameActivity;

public class UnityPlayerGameActivity extends GameActivity
        implements IUnityPlayerLifecycleEvents, IUnityPermissionRequestSupport, IUnityPlayerSupport {
    
    private BroadcastReceiver tokenReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if ("com.sikwin.app.TOKEN_UPDATE".equals(intent.getAction())) {
                String action = intent.getStringExtra("action");
                if ("logout".equals(action)) {
                    Log.d("UnityTokenReceiver", "Received logout signal via broadcast");
                    UnityPlayer.UnitySendMessage("GameManager", "Logout", "");
                } else {
                    String access = intent.getStringExtra("access");
                    String refresh = intent.getStringExtra("refresh");
                    String username = intent.getStringExtra("username");
                    Log.d("UnityTokenReceiver", "Received token update via broadcast");
                    injectTokens(access, refresh, username);
                }
            }
        }
    };

    private void injectTokens(String access, String refresh, String username) {
        try {
            JSONObject json = new JSONObject();
            json.put("access", access);
            json.put("refresh", refresh != null ? refresh : "");
            json.put("username", username != null ? username : "");
            String jsonString = json.toString();

            UnityPlayer.UnitySendMessage("GameManager", "SetAccessAndRefreshTokens", jsonString);
            UnityPlayer.UnitySendMessage("GameManager", "SetToken", access);
            Log.d("UnityTokenReceiver", "Tokens injected into Unity engine");
        } catch (Exception e) {
            Log.e("UnityTokenReceiver", "Error injecting tokens: " + e.getMessage());
        }
    }

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
        
        // Register token receiver for cross-process communication
        IntentFilter filter = new IntentFilter("com.sikwin.app.TOKEN_UPDATE");
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(tokenReceiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(tokenReceiver, filter);
        }
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
        try {
            unregisterReceiver(tokenReceiver);
        } catch (Exception e) {
            // Ignore if already unregistered
        }
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
        Log.d("UnityLoginBypass", "sendLoginDataToUnity called");
        Intent intent = getIntent();
        String token = null;
        String refreshToken = null;
        String username = null;

        if (intent != null) {
            token = intent.getStringExtra("token");
            if (token == null || token.isEmpty()) token = intent.getStringExtra("auth_token");
            if (token == null || token.isEmpty()) token = intent.getStringExtra("access_token");
            refreshToken = intent.getStringExtra("refresh_token");
            username = intent.getStringExtra("username");
        }

        // FALLBACK: Check SharedPreferences if Intent was empty
        if (token == null || token.isEmpty()) {
            Log.d("UnityLoginBypass", "No token in Intent, checking SharedPreferences...");
            String[] prefNames = {"com.company.dicegame.v2.playerprefs", "gunduata_prefs", "UnityPlayerPrefs", "dicegame.v2.playerprefs"};
            String[] tokenKeys = {"auth_token", "user_token", "access_token", "access", "token"};
            
            for (String prefName : prefNames) {
                android.content.SharedPreferences p = getSharedPreferences(prefName, android.content.Context.MODE_PRIVATE);
                for (String key : tokenKeys) {
                    token = p.getString(key, null);
                    if (token != null && !token.isEmpty()) {
                        Log.d("UnityLoginBypass", "Found token in " + prefName + " with key " + key);
                        if (username == null) username = p.getString("username", null);
                        break;
                    }
                }
                if (token != null) break;
            }
        }

        if (token != null && !token.isEmpty()) {
            try {
                JSONObject json = new JSONObject();
                json.put("access", token);
                json.put("refresh", refreshToken != null ? refreshToken : "");
                json.put("username", username != null ? username : "");
                final String jsonString = json.toString();
                final String finalToken = token;

                Log.d("UnityLoginBypass", "Injecting token: " + token.substring(0, Math.min(token.length(), 10)) + "...");

                // Use a Handler to send messages after a short delay to ensure Unity is ready
                android.os.Handler handler = new android.os.Handler(android.os.Looper.getMainLooper());
                
                // Increase delays and frequency to ensure we hit the Unity bridge when it's ready
                long[] delays = { 500, 1000, 2000, 3000, 5000, 8000, 10000 };

                for (long delay : delays) {
                    handler.postDelayed(new Runnable() {
                        @Override
                        public void run() {
                            Log.d("UnityLoginBypass", "Executing delayed injection (" + delay + "ms)");
                            
                // 1. Primary injection
                UnityPlayer.UnitySendMessage("GameManager", "SetAccessAndRefreshTokens", jsonString);
                UnityPlayer.UnitySendMessage("GameManager", "SetToken", finalToken);
                
                // 2. Redundant injection into other common bridge objects
                UnityPlayer.UnitySendMessage("AuthManager", "SetToken", finalToken);
                UnityPlayer.UnitySendMessage("NetworkManager", "SetToken", finalToken);
                
                // 3. Inject base URL to ensure Unity connects to the correct server
                UnityPlayer.UnitySendMessage("GameManager", "SetBaseUrl", "https://gunduata.online/");
                UnityPlayer.UnitySendMessage("GameManager", "SetApiUrl", "https://gunduata.online/api/");
                
                // 4. Trigger auto-login if possible
                UnityPlayer.UnitySendMessage("GameManager", "AutoLogin", "");
                        }
                    }, delay);
                }
            } catch (Exception e) {
                Log.e("UnityLoginBypass", "Error in token injection", e);
            }
        } else {
            Log.d("UnityLoginBypass", "CRITICAL: No token found in Intent or SharedPreferences");
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
