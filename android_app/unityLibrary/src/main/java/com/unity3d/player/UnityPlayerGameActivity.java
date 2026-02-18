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

                                // 1. Inject tokens into GameManager
                                UnityPlayer.UnitySendMessage("GameManager", "SetAccessAndRefreshTokens", jsonString);

                                // 2. Force UIManager to show Gameplay panel (index 3)
                                UnityPlayer.UnitySendMessage("UIManager", "ShowPanel", "3");

                                // 3. Try AutoLoginIfPossible in case it was missed
                                UnityPlayer.UnitySendMessage("UIManager", "AutoLoginIfPossible", "");
                            }
                        }, delay);
                    }

                } catch (Exception e) {
                    Log.e("UnityLoginBypass", "Error setting up login data injection", e);
                }
            } else {
                // FALLBACK: If no token is provided, force Unity to show the Login panel (index
                // 0)
                Log.d("UnityNavigationFix", "No token provided, forcing Login panel (0)");
                android.os.Handler handler = new android.os.Handler(android.os.Looper.getMainLooper());
                long[] delays = { 1000, 2000, 3000, 5000 };
                for (long delay : delays) {
                    handler.postDelayed(new Runnable() {
                        @Override
                        public void run() {
                            UnityPlayer.UnitySendMessage("UIManager", "ShowPanel", "0");
                        }
                    }, delay);
                }
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
