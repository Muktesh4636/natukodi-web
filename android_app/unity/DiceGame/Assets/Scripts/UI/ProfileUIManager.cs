using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class ProfileUIManager : MonoBehaviour
{
    public TextMeshProUGUI balanceAmountText;
    public Button depositBtn;
    public Button withdrawBtn;
    public Button recentBetsBtn;
    public Button transactionHistoryBtn;
    public Button referAndEarnBtn;
    public Button gameRulesBtn;

    private void Start()
    {
        GameManager.Instance.OnWalletUpdated += UpdateWalletAmount;
        depositBtn.onClick.AddListener(() =>
        {
            GetComponentInParent<UserProfileUIManager>().ShowPanel(UserProfilePanelType.Deposit);
        });
        withdrawBtn.onClick.AddListener(() =>
        {
            GetComponentInParent<UserProfileUIManager>().ShowPanel(UserProfilePanelType.Withdraw);
        });
        //recentBetsBtn.onClick.AddListener(() =>
        //{
        //    GetComponentInParent<UserProfileUIManager>().ShowPanel(UserProfilePanelType.RecentBets);
        //});
        //transactionHistoryBtn.onClick.AddListener(() =>
        //{
        //    GetComponentInParent<UserProfileUIManager>().ShowPanel(UserProfilePanelType.TransactionHistory);
        //});
        //referAndEarnBtn.onClick.AddListener(() =>
        //{
        //    GetComponentInParent<UserProfileUIManager>().ShowPanel(UserProfilePanelType.ReferAndEarn);
        //});
        //gameRulesBtn.onClick.AddListener(() =>
        //{
        //    GetComponentInParent<UserProfileUIManager>().ShowPanel(UserProfilePanelType.GameRules);
        //});
    }

    void OnDestroy()
    {
        GameManager.Instance.OnWalletUpdated -= UpdateWalletAmount;
    }

    private void OnEnable()
    {
        UpdateWalletAmount(GameManager.Instance.WalletAmount);
    }

    private void UpdateWalletAmount(float amount)
    {
        balanceAmountText.text = $"₹ {amount:F2}";
    }
}
