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

    private void Awake()
    {
        Instance = this;
        gameplayUIManager = gameplayPanel.GetComponent<GameplayUIManager>();
    }

    public void ShowPanel(UIPanelType panel)
    {
        HideAll();

        switch (panel)
        {
            case UIPanelType.Loading:
                loadingPanel.SetActive(true);
                loadingPanel.GetComponent<LoadingUIManager>().StartLoading();
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
        if (PlayerPrefs.HasKey("username") && PlayerPrefs.HasKey("password"))
        {
            string username = PlayerPrefs.GetString("username");
            string password = PlayerPrefs.GetString("password");

            loginUIManager.LoginUser(username, password);
        }
        else if(PlayerPrefs.HasKey("accessToken") && PlayerPrefs.HasKey("refreshToken"))
        {
            string accessToken = PlayerPrefs.GetString("accessToken");
            string refreshToken = PlayerPrefs.GetString("refreshToken");
            GameManager.Instance.ApiClient.SetAccessAndRefreshToken(accessToken, refreshToken);
            ShowPanel(UIPanelType.Loading);
        }
        else
        {
            ShowPanel(UIPanelType.Register);
        }
    }
}