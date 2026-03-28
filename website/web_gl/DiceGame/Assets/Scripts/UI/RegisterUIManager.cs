using AdvancedInputFieldPlugin;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public enum RegisterErrorType
{
    None,
    InvalidName,
    AlreadyUsedId,
    InvalidPassword,
    WeakPassword,
    MismatchCnfPassword,
}

public class RegisterUIManager : MonoBehaviour
{
    public AdvancedInputField nameInput;
    public AdvancedInputField usernameInput;
    public AdvancedInputField passwordInput;
    public AdvancedInputField confirmPasswordInput;
    public TextMeshProUGUI nameErrorMsg;
    public TextMeshProUGUI idErrorMsg;
    public TextMeshProUGUI passwordErrorMsg;
    public TextMeshProUGUI cnfpasswordErrorMsg;
    public Button passwordHideUnhideBtn;
    public Button cnfPasswordHideUnhideBtn;
    public Button registerBtn;
    public Button showloginPageBtn;
    public Sprite hideIcon;
    public Sprite unhideIcon;

    public string FullName { get { return nameInput.Text; } }
    public string userName { get { return usernameInput.Text; } }
    public string Password { get { return passwordInput.Text; } }
    public string ConfirmPassword { get { return confirmPasswordInput.Text; } }

    private void Start()
    {
        registerBtn.onClick.AddListener(() =>
        {
            RegisterUser();
        });
        passwordHideUnhideBtn.onClick.AddListener(() =>
        {
            passwordInput.VisiblePassword = !passwordInput.VisiblePassword;
            passwordHideUnhideBtn.image.sprite = passwordInput.VisiblePassword == true ? unhideIcon : hideIcon;
        });
        cnfPasswordHideUnhideBtn.onClick.AddListener(() =>
        {
            confirmPasswordInput.VisiblePassword = !confirmPasswordInput.VisiblePassword;
            cnfPasswordHideUnhideBtn.image.sprite = confirmPasswordInput.VisiblePassword == true ? unhideIcon : hideIcon;
        });
        showloginPageBtn.onClick.AddListener(() =>
        {
            UIManager.Instance.ShowPanel(UIPanelType.Login);
        });
    }

    private void OnEnable()
    {
        HideAllErrorMsg();
    }

    public void RegisterUser()
    {
        HideAllErrorMsg();

        if (string.IsNullOrEmpty(FullName))
        {
            ShowErrorMsg(RegisterErrorType.InvalidName);
            return;
        }
        GameManager.Instance.ApiClient.Register(userName, Password, ConfirmPassword, (success, registererror, err) =>
        {
            if (success)
            {
                AndroidToast.Show("Registration Successfull");
                UIManager.Instance.ShowPanel(UIPanelType.Login);
                HideAllErrorMsg();
                ClearAllField();
                return;
            }
            else
            {
                if (registererror == null)
                {
                    Debug.LogError($"Register Error: {err}");
                    return;
                }
                if (registererror.UsernameErrors != null)
                    foreach (var errmsg in registererror.UsernameErrors)
                    {
                        if (errmsg.Contains("A user with that username already exists."))
                        {
                            ShowErrorMsg(RegisterErrorType.AlreadyUsedId);
                            break;
                        }
                    }
                if (registererror.PasswordErrors != null)
                    foreach (var errmsg in registererror.PasswordErrors)
                    {
                        if (errmsg.Contains("This password is too short"))
                        {
                            ShowErrorMsg(RegisterErrorType.InvalidPassword);
                            break;
                        }
                        else if (errmsg.Contains("This password is too common."))
                        {
                            ShowErrorMsg(RegisterErrorType.WeakPassword);
                            break;
                        }
                        else if (errmsg.Contains("Password fields didn't match."))
                        {
                            ShowErrorMsg(RegisterErrorType.MismatchCnfPassword);
                            break;
                        }
                    }
            }
        });
    }

    private void ShowErrorMsg(RegisterErrorType errorType)
    {

        switch (errorType)
        {
            case RegisterErrorType.InvalidName:
                nameErrorMsg.text = "Enter a valid name";
                nameErrorMsg.gameObject.SetActive(true);
                break;
            case RegisterErrorType.AlreadyUsedId:
                idErrorMsg.text = "Email or phone no. already used";
                idErrorMsg.gameObject.SetActive(true);
                break;
            case RegisterErrorType.InvalidPassword:
                passwordErrorMsg.text = "Password must have 4 characters";
                passwordErrorMsg.gameObject.SetActive(true);
                break;
            case RegisterErrorType.WeakPassword:
                passwordErrorMsg.text = "Password is too weak";
                passwordErrorMsg.gameObject.SetActive(true);
                break;
            case RegisterErrorType.MismatchCnfPassword:
                cnfpasswordErrorMsg.text = "Passwords do not match";
                cnfpasswordErrorMsg.gameObject.SetActive(true);
                break;
            default:
                break;
        }
    }

    private void ClearAllField()
    {
        nameInput.Clear();
        usernameInput.Clear();
        passwordInput.Clear();
        confirmPasswordInput.Clear();
    }

    private void HideAllErrorMsg()
    {
        nameErrorMsg.gameObject.SetActive(false);
        idErrorMsg.gameObject.SetActive(false);
        passwordErrorMsg.gameObject.SetActive(false);
        cnfpasswordErrorMsg.gameObject.SetActive(false);
    }
}
