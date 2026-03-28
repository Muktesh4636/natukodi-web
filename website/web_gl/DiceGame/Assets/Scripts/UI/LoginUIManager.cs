using AdvancedInputFieldPlugin;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class LoginUIManager : MonoBehaviour
{
    [Header("Login")]
    public AdvancedInputField loginId;
    public AdvancedInputField loginPassword;
    public TextMeshProUGUI loginErrorMsg;
    public Button passwordHideUnhideBtn;
    public Sprite hideIcon;
    public Sprite unhideIcon;
    public Button loginBtn;
    public Button forgotPassword;
    public Button showregisterPageBtn;

    public string userName { get { return loginId.Text; } }
    public string Password { get { return loginPassword.Text; } }

    private bool isLoginBtnClicked = false;

    private void Start()
    {
        loginBtn.onClick.AddListener(() =>
        {
            isLoginBtnClicked = true;
            LoginUser(userName, Password);
        });
        passwordHideUnhideBtn.onClick.AddListener(() =>
        {
            loginPassword.VisiblePassword = !loginPassword.VisiblePassword;
            passwordHideUnhideBtn.image.sprite = loginPassword.VisiblePassword == true ? unhideIcon : hideIcon;
        });
        showregisterPageBtn.onClick.AddListener(() =>
        {
            UIManager.Instance.ShowPanel(UIPanelType.Register);
        });
    }

    private void OnEnable()
    {
        loginErrorMsg.gameObject.SetActive(false);
    }

    public void LoginUser(string username, string password)
    {
        loginErrorMsg.gameObject.SetActive(false);

        // Guard: prevent double-click spam
        loginBtn.interactable = false;

        GameManager.Instance.ApiClient.Login(username, password, (success, err) =>
        {
            // Ensure UI work runs on main thread (callback already runs on main thread from coroutine,
            // but keep defensive programming)
            try
            {
                if (success)
                {
                    PlayerPrefs.SetString("username", username);
                    PlayerPrefs.SetString("password", password);
                    PlayerPrefs.Save();

                    // If user pressed the login button, show a loading panel (do not reload the scene).
                    // Reloading the scene immediately can destroy/interrupt components and cause the websocket/init
                    // flow to break. Showing the loading panel lets the existing initialization continue.
                    if (isLoginBtnClicked)
                    {
                        isLoginBtnClicked = false;
                        AndroidToast.Show("Login successful");
                        UIManager.Instance.ShowPanel(UIPanelType.Loading);
                    }
                    else
                    {
                        // If login was triggered programmatically (auto-login), go to loading as before.
                        UIManager.Instance.ShowPanel(UIPanelType.Loading);
                    }
                }
                else
                {
                    Debug.Log(err);
                    loginErrorMsg.gameObject.SetActive(true);
                    // re-enable button so user can retry
                    loginBtn.interactable = true;
                }
            }
            catch (System.Exception ex)
            {
                Debug.LogWarning("LoginUser callback error: " + ex.Message);
                loginBtn.interactable = true;
            }
        });
    }

}
