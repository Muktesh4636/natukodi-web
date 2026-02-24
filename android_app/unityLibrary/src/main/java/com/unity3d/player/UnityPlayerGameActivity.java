package com.unity3d.player;

import android.annotation.TargetApi;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.res.Configuration;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.SurfaceView;
import android.widget.FrameLayout;

import androidx.core.view.ViewCompat;

import com.google.androidgamesdk.GameActivity;

import org.json.JSONObject;

public class UnityPlayerGameActivity extends GameActivity implements IUnityPlayerLifecycleEvents, IUnityPermissionRequestSupport, IUnityPlayerSupport
{
    // IMPORTANT:
    // UnitySendMessage invokes the method on *all* MonoBehaviours attached to the target GameObject.
    // Our Unity scene has a GameApiClient MonoBehaviour that exposes SetAccessAndRefreshToken(access, refresh)
    // (2 params), which collides with the 1-param SendMessage signature.
    //
    // To avoid this, we call a "plural" method name that is implemented only by GameManager:
    //   GameManager.SetAccessAndRefreshTokens(string json)
    // and we only do a couple of attempts to avoid spamming.
    private static void sendToGameManager(String method, String payload) {
        new android.os.Handler(android.os.Looper.getMainLooper()).post(new Runnable() {
            @Override
            public void run() {
                try {
                    // Log the attempt
                    Log.d("UnityTokenPass", "UnitySendMessage: " + method);
                    
                    // Send to GameManager object.
                    UnityPlayer.UnitySendMessage("GameManager", method, payload);
                    
                    // Also send to GameApiClient object as a fallback
                    UnityPlayer.UnitySendMessage("GameApiClient", method, payload);
                    
                    // Also send to "Main" as a fallback
                    UnityPlayer.UnitySendMessage("Main", method, payload);
                } catch (Throwable ignored) {
                }
            }
        });
    }

    private BroadcastReceiver tokenReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if ("com.sikwin.app.TOKEN_UPDATE".equals(intent.getAction())) {
                String action = intent.getStringExtra("action");
                if ("logout".equals(action)) {
                    Log.d("UnityTokenReceiver", "Received logout signal via broadcast. Sending Logout to Unity...");
                    
                    // Just send the message to Unity, let Unity handle its own state
                    sendToGameManager("Logout", "");
                    
                    // Safely finish the activity after a short delay to allow Unity to process the message
                    new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(new Runnable() {
                        @Override
                        public void run() {
                            if (!isFinishing() && !isDestroyed()) {
                                Log.d("UnityTokenReceiver", "Finishing Unity activity...");
                                finish();
                            }
                        }
                    }, 500); 
                } else {
                    String access = intent.getStringExtra("access");
                    String refresh = intent.getStringExtra("refresh");
                    Log.d("UnityTokenReceiver", "Received token update via broadcast");
                    // Token-only: do not accept username/password from broadcasts.
                    writeTokensToPlayerPrefsFromBroadcast(access, refresh);
                    // Also set in-memory tokens inside Unity, so early startup API calls don't 401->refresh.
                    injectToUnityInMemory(access, refresh);
                }
            }
        }
    };

    private void injectToUnityInMemory(String access, String refresh) {
        Log.d("UnityTokenReceiver", "injectToUnityInMemory - DISABLED");
        // Disabled access token passing as requested
        return;
    }

    private void writeTokensToPlayerPrefsFromBroadcast(String access, String refresh) {
        Log.d("UnityTokenReceiver", "writeTokensToPlayerPrefsFromBroadcast - DISABLED");
        // Disabled access token passing as requested
        return;
    }

    /**
     * Write tokens to all possible PlayerPrefs files BEFORE Unity loads.
     * GameManager.Start() reads auth_token/access_token/access + refresh_token from PlayerPrefs.
     * Unity uses getPackageName() + ".v2.playerprefs" - write there FIRST.
     */
    private void writeTokensToPlayerPrefsBeforeUnityLoads() {
        Log.d("UnityTokenPass", "writeTokensToPlayerPrefsBeforeUnityLoads - DISABLED");
        // Disabled access token passing as requested
        return;
    }

    class GameActivitySurfaceView extends InputEnabledSurfaceView
    {
        GameActivity mGameActivity;
        public GameActivitySurfaceView(GameActivity activity) {
            super(activity);
            mGameActivity = activity;
        }

        // Reroute motion events from captured pointer to normal events
        // Otherwise when doing Cursor.lockState = CursorLockMode.Locked from C# the touch and mouse events will stop working
        @Override public boolean onCapturedPointerEvent(MotionEvent event) {
            return mGameActivity.onTouchEvent(event);
        }
    }

    protected UnityPlayerForGameActivity mUnityPlayer;
    protected String updateUnityCommandLineArguments(String cmdLine)
    {
        return cmdLine;
    }

    static
    {
        ClassLoader cl = UnityPlayerGameActivity.class.getClassLoader();
        try {
            Class.forName("com.unity3d.player.UnityPlayerForActivityOrService", true, cl);
            Class.forName("com.unity3d.player.UnityPlayerForGameActivity", true, cl);
            Class.forName("com.unity3d.player.UnityPlayer", true, cl);
        } catch (Throwable t) {
            Log.e("UnityPlayerPatch", "Failed to preload Unity glue classes", t);
        }
        try {
            System.loadLibrary("unity");
            System.loadLibrary("il2cpp");
        } catch (Throwable t) {
            Log.e("UnityPlayerPatch", "Failed to preload unity/il2cpp libs", t);
        }
        System.loadLibrary("game");
    }

    @Override
    protected void onCreate(Bundle savedInstanceState){
        super.onCreate(savedInstanceState);
        Log.d("UnityPlayerGameActivity", "onCreate - Ensuring tokens are synced");
        
        // CRITICAL: Pre-load tokens from static holder or Intent before Unity engine starts
        writeTokensToPlayerPrefsBeforeUnityLoads();
        
        // After Unity is created, do a couple of low-frequency attempts to set in-memory tokens/creds.
        // This prevents early unauthenticated calls from triggering 401->refresh without refresh token.
        android.os.Handler handler = new android.os.Handler(android.os.Looper.getMainLooper());
        handler.postDelayed(this::sendLoginDataToUnity, 600);
        handler.postDelayed(this::sendLoginDataToUnity, 1600);
        
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

    // Soft keyboard relies on inset listener for listening to various events - keyboard opened/closed/text entered.
    private void applyInsetListener(SurfaceView surfaceView)
    {
        surfaceView.getViewTreeObserver().addOnGlobalLayoutListener(
                () -> onApplyWindowInsets(surfaceView, ViewCompat.getRootWindowInsets(getWindow().getDecorView())));
    }

    @Override protected InputEnabledSurfaceView createSurfaceView() {
        return new GameActivitySurfaceView(this);
    }

    @Override protected void onCreateSurfaceView() {
        super.onCreateSurfaceView();
        FrameLayout frameLayout = findViewById(contentViewId);

        applyInsetListener(mSurfaceView);

        mSurfaceView.setId(UnityPlayerForGameActivity.getUnityViewIdentifier(this));

        String cmdLine = updateUnityCommandLineArguments(getIntent().getStringExtra("unity"));
        getIntent().putExtra("unity", cmdLine);
        // Unity requires access to frame layout for setting the static splash screen.
        // Note: we cannot initialize in onCreate (after super.onCreate), because game activity native thread would be already started and unity runtime initialized
        //       we also cannot initialize before super.onCreate since frameLayout is not yet available.
        mUnityPlayer = new UnityPlayerForGameActivity(this, frameLayout, mSurfaceView, this);
    }

    @Override
    public void onUnityPlayerUnloaded() {
        moveTaskToBack(true);
    }

    @Override
    public void onUnityPlayerQuitted() {
    }

    // Quit Unity
    @Override protected void onDestroy ()
    {
        try {
            unregisterReceiver(tokenReceiver);
        } catch (Exception e) { }
        if (mUnityPlayer != null) {
            mUnityPlayer.destroy();
            mUnityPlayer = null;
        }
        super.onDestroy();
    }

    @Override protected void onStop()
    {
        // Note: we want Java onStop callbacks to be processed before the native part processes the onStop callback
        if (mUnityPlayer != null) {
            mUnityPlayer.onStop();
        }
        super.onStop();
    }

    @Override protected void onStart()
    {
        // Note: we want Java onStart callbacks to be processed before the native part processes the onStart callback
        Log.d("UnityPlayerGameActivity", "onStart - Ensuring tokens are synced");
        // Write to PlayerPrefs again on start to catch any updates from Kotlin
        writeTokensToPlayerPrefsBeforeUnityLoads();
        if (mUnityPlayer != null) {
            mUnityPlayer.onStart();
        }
        super.onStart();
    }

    // Pause Unity
    @Override protected void onPause()
    {
        // Note: we want Java onPause callbacks to be processed before the native part processes the onPause callback
        if (mUnityPlayer != null) {
            mUnityPlayer.onPause();
        }
        super.onPause();
    }

    // Resume Unity
    @Override protected void onResume()
    {
        // Note: we want Java onResume callbacks to be processed before the native part processes the onResume callback
        Log.d("UnityPlayerGameActivity", "onResume - Proactively injecting credentials and tokens");
        // Write to PlayerPrefs again on resume to catch any updates from Kotlin
        writeTokensToPlayerPrefsBeforeUnityLoads();
        
        if (mUnityPlayer != null) {
            mUnityPlayer.onResume();
            // Single attempt on resume (no retries) to restore in-memory tokens.
            sendLoginDataToUnity();
            
            // Extra attempt to ensure credentials are set if Unity was just initialized
            new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(this::sendLoginDataToUnity, 1000);
        }
        super.onResume();
    }

    // Configuration changes are used by Video playback logic in Unity
    @Override public void onConfigurationChanged(Configuration newConfig)
    {
        if (mUnityPlayer != null) {
            mUnityPlayer.configurationChanged(newConfig);
        }
        super.onConfigurationChanged(newConfig);
    }

    // Notify Unity of the focus change.
    @Override public void onWindowFocusChanged(boolean hasFocus)
    {
        if (mUnityPlayer != null) {
            mUnityPlayer.windowFocusChanged(hasFocus);
        }
        super.onWindowFocusChanged(hasFocus);
    }

    @Override protected void onNewIntent(Intent intent)
    {
        super.onNewIntent(intent);
        // To support deep linking, we need to make sure that the client can get access to
        // the last sent intent. The clients access this through a JNI api that allows them
        // to get the intent set on launch. To update that after launch we have to manually
        // replace the intent with the one caught here.
        setIntent(intent);
        // When activity is reused (singleTask), write tokens - onCreate won't run again
        writeTokensToPlayerPrefsBeforeUnityLoads();
        if (mUnityPlayer != null) {
            mUnityPlayer.newIntent(intent);
        }
        sendLoginDataToUnity();
    }

    @Override
    public void onBackPressed() {
        moveToMainActivity();
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getKeyCode() == KeyEvent.KEYCODE_BACK && event.getAction() == KeyEvent.ACTION_UP) {
            moveToMainActivity();
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    private void moveToMainActivity() {
        try {
            Class<?> mainActivityClass = Class.forName("com.sikwin.app.MainActivity");
            Intent intent = new Intent(this, mainActivityClass);
            intent.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            intent.putExtra("redirect", "home");
            startActivity(intent);
        } catch (ClassNotFoundException e) {
            Log.e("UnityPlayerGameActivity", "MainActivity not found, finishing", e);
            finish();
        }
    }

    public void redirectToForgotPassword() {
        try {
            Log.d("UnityPlayerGameActivity", "Redirecting to Forgot Password screen");
            Class<?> mainActivityClass = Class.forName("com.sikwin.app.MainActivity");
            Intent intent = new Intent(this, mainActivityClass);
            intent.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            intent.putExtra("redirect", "forgot_password");
            startActivity(intent);
        } catch (ClassNotFoundException e) {
            Log.e("UnityPlayerGameActivity", "MainActivity not found during redirect", e);
        }
    }

    private void sendLoginDataToUnity() {
        Log.d("UnityLoginBypass", "sendLoginDataToUnity called - DISABLED");
        // Disabled access token passing as requested
        return;
    }

    @Override
    @TargetApi(Build.VERSION_CODES.M)
    public void requestPermissions(PermissionRequest request)
    {
        if (mUnityPlayer != null) {
            mUnityPlayer.addPermissionRequest(request);
        }
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults)
    {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (mUnityPlayer != null) {
            mUnityPlayer.permissionResponse(this, requestCode, permissions, grantResults);
        }
    }
}
