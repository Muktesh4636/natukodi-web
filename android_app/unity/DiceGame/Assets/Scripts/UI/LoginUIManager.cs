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
        forgotPassword.onClick.AddListener(() =>
        {
            Debug.Log("[LoginUIManager] Forgot Password clicked, calling native redirect");
            try
            {
                using (AndroidJavaClass jc = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                {
                    using (AndroidJavaObject jo = jc.GetStatic<AndroidJavaObject>("currentActivity"))
                    {
                        jo.Call("redirectToForgotPassword");
                    }
                }
            }
            catch (System.Exception e)
            {
                Debug.LogError("[LoginUIManager] Failed to call redirectToForgotPassword: " + e.Message);
                // Fallback: maybe show a Unity-based message or just do nothing
            }
        });
    }

    private void OnEnable()
    {
        loginErrorMsg.gameObject.SetActive(false);
    }

    public void LoginUser(string username, string password)
    {
        if (string.IsNullOrEmpty(username) || string.IsNullOrEmpty(password))
        {
            Debug.LogWarning("[LoginUIManager] LoginUser called with empty credentials");
            UIManager.Instance.ShowPanel(UIPanelType.Login);
            return;
        }

        Debug.Log("[LoginUIManager] LoginUser called for: " + username);
        loginErrorMsg.gameObject.SetActive(false);
        GameManager.Instance.ApiClient.Login(username, password, (success, err) =>
        {
            if (success)
            {
                Debug.Log("[LoginUIManager] Login success for: " + username);
                PlayerPrefs.SetString("username", username);
                PlayerPrefs.SetString("password", password);
                PlayerPrefs.SetInt("is_logged_in", 1);
                PlayerPrefs.Save();

                if (isLoginBtnClicked)
                {
                    isLoginBtnClicked = false;
                    AndroidToast.Show("Logging Successfull");
                    SceneManager.LoadScene(SceneManager.GetActiveScene().buildIndex);
                }
                else
                {
                    Debug.Log("[LoginUIManager] Auto-login success, showing gameplay");
                    UIManager.Instance.ShowPanel(UIPanelType.Gameplay);
                    loginErrorMsg.gameObject.SetActive(false);
                }
            }
            else
            {
                Debug.LogError("[LoginUIManager] Login failed for " + username + ": " + err);
                loginErrorMsg.gameObject.SetActive(true);
                // If auto-login failed, make sure we show the login panel
                UIManager.Instance.ShowPanel(UIPanelType.Login);
            }
        });
    }

}
