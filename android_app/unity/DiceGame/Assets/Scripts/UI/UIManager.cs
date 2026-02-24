using UnityEngine;

public enum UIPanelType
{
    Loading,
    Login,
    Register,
    UserProfile,
    Gameplay
}

public class UIManager : MonoBehaviour
{
    public static UIManager Instance;

    [SerializeField] private GameObject loginPanel;
    [SerializeField] private GameObject registerPanel;
    [SerializeField] private GameObject userProfilePanel;
    [SerializeField] private GameObject gameplayPanel;
    [SerializeField] private GameObject noInternetPanel;
    [SerializeField] private GameObject loadingPanel;

    private LoginUIManager loginUIManager => loginPanel.GetComponent<LoginUIManager>();
    public GameplayUIManager gameplayUIManager { get; private set; }

    private bool TryResolveTokens(out string access, out string refresh)
    {
        access = null;
        refresh = null;

        // 1) Unity PlayerPrefs (fast path)
        string token = PlayerPrefs.GetString("auth_token", "");
        if (string.IsNullOrEmpty(token)) token = PlayerPrefs.GetString("access_token", "");
        if (string.IsNullOrEmpty(token)) token = PlayerPrefs.GetString("access", "");
        if (!string.IsNullOrEmpty(token))
        {
            access = token;
            refresh = PlayerPrefs.GetString("refresh_token", "");
            if (string.IsNullOrEmpty(refresh)) refresh = PlayerPrefs.GetString("refresh", "");
            if (string.IsNullOrEmpty(refresh)) refresh = PlayerPrefs.GetString("refreshToken", "");
            Debug.Log("[UIManager] TryResolveTokens: Found token in PlayerPrefs (len=" + access.Length + ")");
            return true;
        }

        // 2) In-memory token already injected into ApiClient
        if (GameManager.Instance != null && GameManager.Instance.ApiClient != null && GameManager.Instance.ApiClient.HasAccessToken)
        {
            access = GameManager.Instance.ApiClient.CurrentAccessToken;
            refresh = GameManager.Instance.ApiClient.CurrentRefreshToken;
            Debug.Log("[UIManager] TryResolveTokens: Found token in ApiClient (len=" + (access != null ? access.Length : 0) + ")");
            return !string.IsNullOrEmpty(access);
        }

#if UNITY_ANDROID && !UNITY_EDITOR
        // 3) Java UnityTokenHolder (covers timing where PlayerPrefs not yet visible)
        try
        {
            var holder = new UnityEngine.AndroidJavaClass("com.unity3d.player.UnityTokenHolder");
            access = holder.CallStatic<string>("getAccessToken");
            refresh = holder.CallStatic<string>("getRefreshToken");
            if (!string.IsNullOrEmpty(access))
                Debug.Log("[UIManager] TryResolveTokens: Found token in Java holder (len=" + access.Length + ")");
            return !string.IsNullOrEmpty(access);
        }
        catch (System.Exception ex)
        {
            Debug.LogWarning("[UIManager] TryResolveTokens: Java holder failed: " + ex.Message);
        }
#endif

        return false;
    }

    private void Awake()
    {
        Instance = this;
        gameplayUIManager = gameplayPanel.GetComponent<GameplayUIManager>();
        // Ensure Android UnitySendMessage("UIManager", ...) always finds this object
        gameObject.name = "UIManager";

        // Token-only flow: if a token exists, avoid briefly showing Login/Register.
        if (TryResolveTokens(out var access, out _))
        {
            Debug.Log("[UIManager] Awake: Token detected (len=" + (access != null ? access.Length : 0) + "), hiding login panel");
            HideAll();
            loadingPanel.SetActive(true);
        }
    }

    /// <summary>Called from Android via UnitySendMessage - accepts "0"=Loading, "1"=Login, "2"=Register, "3"=UserProfile, "4"=Gameplay</summary>
    public void ShowPanel(string panelIndex)
    {
        if (int.TryParse(panelIndex, out int idx) && idx >= 0 && idx <= 4)
            ShowPanel((UIPanelType)idx);
    }

    public void ShowPanel(UIPanelType panel)
    {
        // Token-only guard: if we already have a token (prefs or injected into ApiClient),
        // do not allow switching back to Login/Register due to timing/race conditions.
        if (panel == UIPanelType.Login || panel == UIPanelType.Register)
        {
            if (TryResolveTokens(out _, out _))
            {
                Debug.Log("[UIManager] ShowPanel: Token exists, ignoring Login/Register request");
                panel = UIPanelType.Gameplay;
            }
        }

        HideAll();

        switch (panel)
        {
            case UIPanelType.Loading:
                loadingPanel.SetActive(true);
                break;
            case UIPanelType.Login:
                loginPanel.SetActive(true);
                break;
            case UIPanelType.Register:
                registerPanel.SetActive(true);
                break;
            case UIPanelType.UserProfile:
                userProfilePanel.SetActive(true);
                break;
            case UIPanelType.Gameplay:
                gameplayPanel.SetActive(true);
                break;
        }
    }

    private void HideAll()
    {
        loadingPanel?.SetActive(false);
        loginPanel?.SetActive(false);
        registerPanel?.SetActive(false);
        userProfilePanel?.SetActive(false);
        gameplayPanel?.SetActive(false);
    }

    public void ShowNoInternetPopup(bool show)
    {
        noInternetPanel.SetActive(show);
    }

    public void AutoLoginIfPossible()
    {
        // Token-only flow: bootstrap with token from any available source.
        if (TryResolveTokens(out var token, out var refresh))
        {
            Debug.Log("[UIManager] AutoLogin: Found token in PlayerPrefs, showing gameplay");
            if (GameManager.Instance != null)
                GameManager.Instance.BootstrapWithToken(token, refresh);
            else
                ShowPanel(UIPanelType.Gameplay);
            return;
        }

        Debug.Log("[UIManager] AutoLogin: No tokens found, showing login panel");
        ShowPanel(UIPanelType.Login);
    }
}