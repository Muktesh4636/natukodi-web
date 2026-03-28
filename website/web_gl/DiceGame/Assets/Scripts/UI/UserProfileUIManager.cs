using AdvancedInputFieldPlugin;
using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public enum UserProfilePanelType
{
    Deposit,
    Profile,
    Withdraw,
    TransactionHistory,
    RecentBets,
    ReferAndEarn,
    GameRules
}

public class UserProfileUIManager : MonoBehaviour
{
    public TextMeshProUGUI usernameText;
    public TextMeshProUGUI joinDateText;
    public AdvancedInputField editPlayerNameIF;

    public Sprite depositSelect;
    public Sprite depositUnselect;
    public Sprite profileSelect;
    public Sprite profileUnselect;

    public Button LogoutBtn;
    public Button depositBtn;
    public Button profileBtn;
    public Button playGunduAtaBtn;
    public Button EditPlayerNameBtn;

    public DepositUIManager deposituimanager;
    public ProfileUIManager profileuimanager;
    public WithdrawUIManager WithdrawUIManager;

    private void Start()
    {
        depositBtn.onClick.AddListener(() =>
        {
            ShowPanel(UserProfilePanelType.Deposit);
        });
        profileBtn.onClick.AddListener(() =>
        {
            ShowPanel(UserProfilePanelType.Profile);
        });
        EditPlayerNameBtn.onClick.AddListener(EditPlayerName);
        LogoutBtn.onClick.AddListener(Logout);
        playGunduAtaBtn.onClick.AddListener(OnPlayGunduAtaButtonClicked);

        editPlayerNameIF.gameObject.SetActive(false);
    }

    private void OnEnable()
    {
        ShowPanel(UserProfilePanelType.Profile);
    }

    public void ShowPanel(UserProfilePanelType panel)
    {
        HideAll();

        switch (panel)
        {
            case UserProfilePanelType.Deposit:
                deposituimanager.gameObject.SetActive(true);
                UpdateButtonVisuals(depositSelected: true);
                break;
            case UserProfilePanelType.Profile:
                profileuimanager.gameObject.SetActive(true);
                UpdateButtonVisuals(depositSelected: false);
                break;
            case UserProfilePanelType.Withdraw:
                WithdrawUIManager.gameObject.SetActive(true);
                break;
            case UserProfilePanelType.TransactionHistory:
                break;
            case UserProfilePanelType.RecentBets:
                break;
            case UserProfilePanelType.ReferAndEarn:
                break;
            case UserProfilePanelType.GameRules:
                break;
        }
    }

    private void HideAll()
    {
        deposituimanager.gameObject.SetActive(false);
        profileuimanager.gameObject.SetActive(false);
        WithdrawUIManager.gameObject.SetActive(false);
    }

    private void OnPlayGunduAtaButtonClicked()
    {
        UIManager.Instance.ShowPanel(UIPanelType.Gameplay);
    }

    private void Logout()
    {
        PlayerPrefs.DeleteKey("username");
        PlayerPrefs.DeleteKey("password");
        UIManager.Instance.ShowPanel(UIPanelType.Login);
    }

    private void EditPlayerName()
    {
        editPlayerNameIF.Text = usernameText.text;
        editPlayerNameIF.gameObject.SetActive(true);
        usernameText.gameObject.SetActive(false);
        editPlayerNameIF.OnEndEdit.AddListener((string newName, EndEditReason editendreason) =>
        {
            if (!string.IsNullOrEmpty(newName))
            {
                usernameText.text = newName.ToUpper();
            }
            editPlayerNameIF.gameObject.SetActive(false);
            usernameText.gameObject.SetActive(true);
        });
        //editPlayerNameIF.OnValueChanged.AddListener((string val) =>
        //{
        //    editPlayerNameIF.Text = val.ToUpper();
        //});
        editPlayerNameIF.ManualSelect();
    }

    private void UpdateButtonVisuals(bool depositSelected)
    {
        if (depositSelected)
        {
            depositBtn.transform.GetChild(1).GetComponent<Image>().sprite = depositSelect;
            profileBtn.transform.GetChild(1).GetComponent<Image>().sprite = profileUnselect;
        }
        else
        {
            depositBtn.transform.GetChild(1).GetComponent<Image>().sprite = depositUnselect;
            profileBtn.transform.GetChild(1).GetComponent<Image>().sprite = profileSelect;
        }
    }

}
