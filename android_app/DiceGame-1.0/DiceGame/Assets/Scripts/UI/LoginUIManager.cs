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
        GameManager.Instance.ApiClient.Login(username, password, (success, err) =>
        {
            if (success)
            {
                PlayerPrefs.SetString("username", username);
                PlayerPrefs.SetString("password", password);
                if (isLoginBtnClicked)
                {
                    isLoginBtnClicked = false;
                    AndroidToast.Show("Logging Successfull");
                    SceneManager.LoadScene(SceneManager.GetActiveScene().buildIndex);
                }
                else
                {
                    UIManager.Instance.ShowPanel(UIPanelType.Gameplay);
                    loginErrorMsg.gameObject.SetActive(false);
                }
            }
            else
            {
                Debug.Log(err);
                loginErrorMsg.gameObject.SetActive(true);
            }
        });
    }

}
