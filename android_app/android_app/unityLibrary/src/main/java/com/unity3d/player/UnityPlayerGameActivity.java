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
        try {
            Class.forName("com.unity3d.player.UnityPlayerForActivityOrService");
            Class.forName("com.unity3d.player.UnityPlayerForGameActivity");
        } catch (Throwable t) {
            Log.e("UnityPlayerPatch", "Failed to preload Unity glue classes", t);
        }
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
        try {
            mUnityPlayer = new UnityPlayerForGameActivity(this, frameLayout, mSurfaceView, this);
        } catch (Throwable t) {
            Log.e("UnityPlayerGameActivity", "Failed to create Unity player", t);
            finish();
        }
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
        if (mUnityPlayer != null) {
            mUnityPlayer.destroy();
            mUnityPlayer = null;
        }
        super.onDestroy();
    }

    @Override
    protected void onStop() {
        if (mUnityPlayer != null) {
            mUnityPlayer.onStop();
        }
        super.onStop();
    }

    @Override
    protected void onStart() {
        if (mUnityPlayer != null) {
            mUnityPlayer.onStart();
        }
        super.onStart();
    }

    // Pause Unity
    @Override
    protected void onPause() {
        if (mUnityPlayer != null) {
            mUnityPlayer.onPause();
        }
        super.onPause();
    }

    // Resume Unity
    @Override
    protected void onResume() {
        if (mUnityPlayer != null) {
            mUnityPlayer.onResume();
            sendLoginDataToUnity();
            addProfileOverlay();
            addBalanceOverlay();
        }
        super.onResume();
    }

    // Configuration changes are used by Video playback logic in Unity
    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        if (mUnityPlayer != null) {
            mUnityPlayer.configurationChanged(newConfig);
        }
        super.onConfigurationChanged(newConfig);
    }

    // Notify Unity of the focus change.
    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        if (mUnityPlayer != null) {
            mUnityPlayer.windowFocusChanged(hasFocus);
        }
        super.onWindowFocusChanged(hasFocus);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (mUnityPlayer != null) {
            mUnityPlayer.newIntent(intent);
        }
    }

    @Override
    @TargetApi(Build.VERSION_CODES.M)
    public void requestPermissions(PermissionRequest request) {
        if (mUnityPlayer != null) {
            mUnityPlayer.addPermissionRequest(request);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (mUnityPlayer != null) {
            mUnityPlayer.permissionResponse(this, requestCode, permissions, grantResults);
        }
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
        Intent intent = getIntent();
        if (intent != null) {
            final String token = intent.getStringExtra("token");
            final String refreshToken = intent.getStringExtra("refresh_token");
            final String username = intent.getStringExtra("username");
            final String password = intent.getStringExtra("password");

            if (token != null && !token.isEmpty()) {
                try {
                    JSONObject json = new JSONObject();
                    json.put("access", token);
                    json.put("refresh", refreshToken);
                    final String jsonString = json.toString();

                    Log.d("UnityLoginBypass", "Preparing to send login data to Unity...");

                    // Use a Handler to send messages after a short delay to ensure Unity is ready
                    android.os.Handler handler = new android.os.Handler(android.os.Looper.getMainLooper());

                    // Try injection multiple times with different delays to hit the right window
                    long[] delays = { 1000, 2000, 3000, 5000 };

                    for (long delay : delays) {
                        handler.postDelayed(new Runnable() {
                            @Override
                            public void run() {
                                Log.d("UnityLoginBypass", "Executing delayed injection (delay: " + delay + "ms)");

                                // Inject only token payload; avoid forcing panel API calls
                                // because method names vary between Unity builds.
                                UnityPlayer.UnitySendMessage("GameManager", "SetAccessAndRefreshTokens", jsonString);
                            }
                        }, delay);
                    }

                } catch (Exception e) {
                    Log.e("UnityLoginBypass", "Error setting up login data injection", e);
                }
            } else {
                // No token provided: keep Unity default panel flow.
                Log.d("UnityNavigationFix", "No token provided, using Unity default panel flow");
            }
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
