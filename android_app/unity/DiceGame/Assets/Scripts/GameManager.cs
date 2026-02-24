using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;
using static GameApiClient;

public class GameManager : MonoBehaviour
{
    public static GameManager Instance { get; private set; }

    [Header("API")]
    [SerializeField] private GameApiClient apiClient;

    public GameApiClient ApiClient => apiClient;

    public float WalletAmount { get; private set; }
    public GameSettings GameSettings { get; private set; }
    public Action<float> OnWalletUpdated;

    public int loadingTime {get; private set; }

    private string lastInjectedToken = null;

    private void Awake()
    {
        Debug.Log("[GameManager] Awake - Application.identifier=" + Application.identifier);
        Application.targetFrameRate = 60;
        loadingTime = 8; // Default loading time, will be updated from server
        if (Instance != null)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;
        DontDestroyOnLoad(gameObject);
        // Ensure Android UnitySendMessage("GameManager", ...) always finds this object
        gameObject.name = "GameManager";

        // Token-only flow: read tokens immediately from Java holder (fastest path)
#if UNITY_ANDROID && !UNITY_EDITOR
        try
        {
            var holder = new UnityEngine.AndroidJavaClass("com.unity3d.player.UnityTokenHolder");
            string token = holder.CallStatic<string>("getAccessToken");
            string refresh = holder.CallStatic<string>("getRefreshToken");

            if (!string.IsNullOrEmpty(token))
            {
                Debug.Log("[GameManager] Awake: Token found in Java holder (len=" + token.Length + ")");
                PlayerPrefs.SetInt("is_logged_in", 1);
                PlayerPrefs.Save();

                // CRITICAL: If we have a token in Awake, bootstrap immediately
                // This ensures InitWebSocket and ShowPanel(Gameplay) happen as early as possible.
                BootstrapWithToken(token, refresh);
                lastInjectedToken = token;
            }
            else
            {
                Debug.Log("[GameManager] Awake: No token in Java holder");
            }
        }
        catch (System.Exception ex) { Debug.LogWarning("[GameManager] Java Holder check failed in Awake: " + ex.Message); }
#endif
    }

    private void Start()
    {
        ApiClient.OnLoginSuccess += FetchInitialData;

        // Token-only hard-bypass: check ALL possible sources for tokens and bootstrap gameplay.
        Debug.Log("[GameManager] Start - Token hard-bypass initiated");
        string token = null;
        string refresh = null;
        
        // Source 1: Unity PlayerPrefs
        if (PlayerPrefs.HasKey("auth_token")) token = PlayerPrefs.GetString("auth_token");
        if (string.IsNullOrEmpty(token) && PlayerPrefs.HasKey("access_token")) token = PlayerPrefs.GetString("access_token");
        if (string.IsNullOrEmpty(token) && PlayerPrefs.HasKey("access")) token = PlayerPrefs.GetString("access");
        if (PlayerPrefs.HasKey("refresh_token")) refresh = PlayerPrefs.GetString("refresh_token");
        if (string.IsNullOrEmpty(refresh) && PlayerPrefs.HasKey("refresh")) refresh = PlayerPrefs.GetString("refresh");
        if (string.IsNullOrEmpty(refresh) && PlayerPrefs.HasKey("refreshToken")) refresh = PlayerPrefs.GetString("refreshToken");

#if UNITY_ANDROID && !UNITY_EDITOR
        // Source 2: Java Holder (Retry in Start if Awake missed it)
        if (string.IsNullOrEmpty(token))
        {
            try
            {
                var holder = new UnityEngine.AndroidJavaClass("com.unity3d.player.UnityTokenHolder");
                if (string.IsNullOrEmpty(token)) token = holder.CallStatic<string>("getAccessToken");
                if (string.IsNullOrEmpty(refresh)) refresh = holder.CallStatic<string>("getRefreshToken");
            }
            catch (System.Exception) {}
        }

        // Source 3: Direct Android SharedPreferences (Deep Scan)
        if (string.IsNullOrEmpty(token))
        {
            try
            {
                var unityPlayer = new UnityEngine.AndroidJavaClass("com.unity3d.player.UnityPlayer");
                var activity = unityPlayer.GetStatic<UnityEngine.AndroidJavaObject>("currentActivity");
                var ctx = activity.Call<UnityEngine.AndroidJavaObject>("getApplicationContext");
                string pkg = ctx.Call<string>("getPackageName");
                
                string[] prefFiles = { 
                    pkg + ".v2.playerprefs", 
                    "com.sikwin.app.v2.playerprefs", 
                    "gunduata_prefs", 
                    "com.company.dicegame.v2.playerprefs",
                    pkg + "_preferences",
                    "PlayerPrefs"
                };

                foreach (string fileName in prefFiles)
                {
                    var sharedPrefs = ctx.Call<UnityEngine.AndroidJavaObject>("getSharedPreferences", fileName, 0);
                    if (sharedPrefs == null) continue;

                    if (string.IsNullOrEmpty(token)) token = sharedPrefs.Call<string>("getString", "auth_token", null);
                    if (string.IsNullOrEmpty(token)) token = sharedPrefs.Call<string>("getString", "access_token", null);
                    if (string.IsNullOrEmpty(token)) token = sharedPrefs.Call<string>("getString", "access", null);

                    if (string.IsNullOrEmpty(refresh)) refresh = sharedPrefs.Call<string>("getString", "refresh_token", null);
                    if (string.IsNullOrEmpty(refresh)) refresh = sharedPrefs.Call<string>("getString", "refresh", null);
                    if (string.IsNullOrEmpty(refresh)) refresh = sharedPrefs.Call<string>("getString", "refreshToken", null);
                    
                    if (!string.IsNullOrEmpty(token)) break;
                }
            }
            catch (System.Exception ex) { Debug.LogWarning("[GameManager] Deep scan failed: " + ex.Message); }
        }
#endif

        // DECISION: If we have tokens, bootstrap and FORCE gameplay screen
        if (!string.IsNullOrEmpty(token))
        {
            Debug.Log("[GameManager] Token hard-bypass: Found token. Forcing gameplay.");
            BootstrapWithToken(token, refresh);
            return;
        }
        
        Debug.Log("[GameManager] Token hard-bypass: No token found, defaulting to UIManager logic");
        if (UIManager.Instance != null) UIManager.Instance.AutoLoginIfPossible();

        // IMPORTANT: Run non-critical startup calls AFTER token bootstrap.
        // If these run before tokens are set, they can 401 and trigger a refresh attempt with empty refreshToken.
        ApiClient.GetLoadingTime((ok, time, err) =>
        {
            if (ok)
                loadingTime = time.loading_time;
        });
        ApiClient.GetSoundSettings((ok, settings, err) =>
        {
            if (ok && settings != null)
                AudioManager.Instance.SetBackgroundMusicVolume(settings.BackgroundMusicVolume);
        });
    }

    public void BootstrapWithToken(string access, string refresh)
    {
        if (string.IsNullOrEmpty(access)) return;
        Debug.Log("[GameManager] BootstrapWithToken: accessLen=" + access.Length + " refreshLen=" + (string.IsNullOrEmpty(refresh) ? 0 : refresh.Length));

        // Persist token into Unity PlayerPrefs so UIManager/token checks work reliably,
        // even if tokens arrived via Android broadcast/UnitySendMessage after startup.
        PlayerPrefs.SetString("auth_token", access);
        PlayerPrefs.SetString("access_token", access);
        PlayerPrefs.SetString("access", access);
        if (!string.IsNullOrEmpty(refresh))
        {
            PlayerPrefs.SetString("refresh_token", refresh);
            PlayerPrefs.SetString("refresh", refresh);
            PlayerPrefs.SetString("refreshToken", refresh);
        }
        PlayerPrefs.SetInt("is_logged_in", 1);
        // Token-only cleanup: remove any stale credentials from old flows
        PlayerPrefs.DeleteKey("username");
        PlayerPrefs.DeleteKey("password");
        PlayerPrefs.DeleteKey("user_pass");
        PlayerPrefs.Save();

        apiClient.SetTokens(access, refresh);
        apiClient.InitWebSocket();
        FetchInitialData();
        
        // Ensure we are showing the Gameplay panel
        if (UIManager.Instance != null)
        {
            Debug.Log("[GameManager] Bootstrap: Forcing Gameplay panel");
            UIManager.Instance.ShowPanel(UIPanelType.Gameplay);
        }
    }

    private void FetchInitialData()
    {
        apiClient.GetGameSettings((ok, settings, err) =>
        {
            if (ok && settings != null)
                GameSettings = settings;
        });

        RefreshWallet();
    }

    public void RefreshWallet()
    {
        apiClient.GetWallet((ok, wallet, err) =>
        {
            if (ok && wallet != null)
            {
                WalletAmount = float.Parse(wallet.balance);
                OnWalletUpdated?.Invoke(WalletAmount);
            }
        });
    }

    /// <summary>Called from Kotlin/Android via UnitySendMessage - accepts {"accessToken","refreshToken"} or {"access","refresh"}</summary>
    public void SetAccessAndRefreshToken(string json)
    {
        Debug.Log("[GameManager] SetAccessAndRefreshToken called with: " + json);
        if (string.IsNullOrEmpty(json)) return;
        try
        {
            var obj = JObject.Parse(json);
            string access = obj["accessToken"]?.ToString() ?? obj["access"]?.ToString();
            string refresh = obj["refreshToken"]?.ToString() ?? obj["refresh"]?.ToString();
            Debug.Log("[GameManager] Parsed access: " + (string.IsNullOrEmpty(access) ? "null" : access.Substring(0, Math.Min(access.Length, 10)) + "...") + ", refresh: " + (string.IsNullOrEmpty(refresh) ? "null" : refresh.Substring(0, Math.Min(refresh.Length, 10)) + "..."));
            
            if (!string.IsNullOrEmpty(access))
            {
                if (access == lastInjectedToken)
                {
                    Debug.Log("[GameManager] Token already injected, skipping InitWebSocket");
                    return;
                }
                lastInjectedToken = access;

                Debug.Log("[GameManager] Tokens set via SetAccessAndRefreshToken successfully");
                BootstrapWithToken(access, refresh);
            }
            else
            {
                Debug.LogWarning("[GameManager] Access token is null or empty in JSON");
            }
        }
        catch (Exception ex)
        {
            Debug.LogError("[GameManager] SetAccessAndRefreshToken error: " + ex.Message);
        }
    }

    public void SetAccessAndRefreshTokens(string json) => SetAccessAndRefreshToken(json);

    public void Logout(string dummy)
    {
        Debug.Log("[GameManager] Logout called from Kotlin - Resetting state and clearing PlayerPrefs");
        lastInjectedToken = null;
        if (apiClient != null)
        {
            apiClient.SetTokens(null, null);
            apiClient.CloseWebSocket();
        }
        
        // Clear all PlayerPrefs to ensure no stale data persists
        PlayerPrefs.DeleteAll();
        PlayerPrefs.Save();
        
        // Stop all local activity
        StopAllCoroutines();
        
        var gameController = FindFirstObjectByType<GameController>();
        if (gameController != null)
        {
            gameController.ResetState();
        }
        
        if (UIManager.Instance != null)
        {
            UIManager.Instance.ShowPanel(UIPanelType.Login);
        }
    }

    public void AutoLogin(string dummy)
    {
        if (UIManager.Instance != null)
            UIManager.Instance.AutoLoginIfPossible();
    }

    public void SetToken(string token)
    {
        if (!string.IsNullOrEmpty(token))
        {
            apiClient.SetTokens(token, null);
            apiClient.InitWebSocket();
            FetchInitialData();
            if (UIManager.Instance != null)
                UIManager.Instance.ShowPanel(UIPanelType.Gameplay);
        }
    }

    public void ShowGameplayFromAndroid()
    {
        if (UIManager.Instance != null)
            UIManager.Instance.ShowPanel(UIPanelType.Gameplay);
    }

    public void SetBaseUrl(string url) => apiClient.SetBaseUrl(url);
    public void SetApiUrl(string url) => apiClient.SetApiUrl(url);
    public void SetWsUrl(string url) => apiClient.SetWsUrl(url);

    /// <summary>Called from Kotlin/Android via UnitySendMessage - accepts {"username","password"}. Saves to PlayerPrefs for AutoLoginIfPossible.</summary>
    public void SetLoginCredential(string json)
    {
        if (string.IsNullOrEmpty(json)) return;
        try
        {
            var obj = JObject.Parse(json);
            string username = obj["username"]?.ToString();
            string password = obj["password"]?.ToString();
            if (!string.IsNullOrEmpty(username) && !string.IsNullOrEmpty(password))
            {
                PlayerPrefs.SetString("username", username);
                PlayerPrefs.SetString("password", password);
                PlayerPrefs.Save();
                Debug.Log("[GameManager] Login credential saved from Kotlin");
            }
        }
        catch (Exception ex)
        {
            Debug.LogError("[GameManager] SetLoginCredential error: " + ex.Message);
        }
    }

    // 🔒 Future-ready
    // public void RegisterUser(...) {}
    // public void Deposit(...) {}
}