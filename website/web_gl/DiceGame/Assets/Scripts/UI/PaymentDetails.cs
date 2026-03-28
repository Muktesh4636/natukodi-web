using System.Runtime.CompilerServices;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public enum PaymentType
{
    Bank,
    UPI
}
public struct PaymentDetailsData
{
    public int id;
    public PaymentType paymentType;
    public string BankName;
    public string BankAccountNumber;
    public string AccountHolderName;
    public string IfscCode;
    public string upiId;
}


public class PaymentDetails : MonoBehaviour
{
    public TextMeshProUGUI detailsText;
    public Button removeAccount;
    public GameObject selectedGlowObj;

    private Button paymentDetailsObjBtn;
    private PaymentDetailsData paymentDetailsData;
    private WithdrawUIManager withdrawUIManager;

    private void Awake()
    {
        withdrawUIManager = GetComponentInParent<WithdrawUIManager>();
        paymentDetailsObjBtn = GetComponent<Button>();
        removeAccount.onClick.AddListener(RemoveAccount);
        paymentDetailsObjBtn.onClick.AddListener(() =>
        {
            SetSelectedState(true);
        });
    }

    public void setPaymentDetailsData(PaymentDetailsData data)
    {
        paymentDetailsData = data;
        string details = paymentDetailsData.BankName + " - ";

        if (paymentDetailsData.paymentType == PaymentType.UPI)
        {
            //details += MaskUpiId(upiID);
            details += paymentDetailsData.upiId;
        }
        else if (paymentDetailsData.paymentType == PaymentType.Bank)
        {
            //details += MaskBankAccount(bankAccountNumber);
            details += paymentDetailsData.BankAccountNumber;
        }

        detailsText.text = details;
    }

    public void SetSelectedState(bool isSelected)
    {
        selectedGlowObj.SetActive(isSelected);
        if (isSelected)
            withdrawUIManager.SetSelectedPaymentDetail(paymentDetailsData.id);
    }

    public int GetId()
    {
        return paymentDetailsData.id;
    }

    public PaymentDetailsData GetPaymentDetailsData()
    {
        return paymentDetailsData;
    }

    private void RemoveAccount()
    {
        withdrawUIManager.RemoveUserAccountDetail(paymentDetailsData.id);
    }

    private string MaskBankAccount(string accountNumber)
    {
        if (accountNumber.Length < 4)
            return "****";

        string last4 = accountNumber.Substring(accountNumber.Length - 4);
        return "**** **** " + last4;
    }

    private string MaskUpiId(string upiId)
    {
        int atIndex = upiId.IndexOf('@');
        if (atIndex <= 0)
            return "****";

        string firstPart = upiId.Substring(0, Mathf.Min(4, atIndex));
        string domainPart = upiId.Substring(atIndex); // includes '@'

        return firstPart + "*****" + domainPart;
    }
}
