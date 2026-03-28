using AdvancedInputFieldPlugin;
using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class WithdrawUIManager : MonoBehaviour
{
    public TextMeshProUGUI balanceAmountText;
    public GameObject userpaymentDetailsPrefab;
    public AdvancedInputField amountIF;
    public Button backToProfileBtn;
    public Button addBankAccountBtn;
    public Button addUPIBtn;
    public Button withdrawBtn;
    public GameObject paymentDetailsObj;

    [Header("Add Bank and UPI Details")]
    public GameObject bankAndUpiDetailPopup;
    public GameObject bankDetailsObj;
    public GameObject upiDetailsObj;
    public GameObject parentContentObj;

    [Header("Bank Details")]
    public AdvancedInputField bankNameIF;
    public AdvancedInputField accountHolderNameIF;
    public AdvancedInputField accountNumberIF;
    public AdvancedInputField ifscCodeIF;
    public Button addBankDetailsBtn;
    public Button cancelBankDetailsBtn;

    [Header("UPI Details")]
    public AdvancedInputField upiBankNameIF;
    public AdvancedInputField upiIdIF;
    public Button addUpiDetailsBtn;
    public Button cancelUpiDetailsBtn;

    private int amountToWithdraw = 0;
    private PaymentDetailsData selectedPayment;
    private List<PaymentDetails> details = new List<PaymentDetails>(); 
    private int paymentDetailIdCounter = 1;

    private void Start()
    {
        GameManager.Instance.OnWalletUpdated += UpdateWalletAmount;
        backToProfileBtn.onClick.AddListener(() =>
        {
            GetComponentInParent<UserProfileUIManager>().ShowPanel(UserProfilePanelType.Profile);
        });
        addBankAccountBtn.onClick.AddListener(() =>
        {
            ShowPaymentDetailsPopup(true);
        });
        addUPIBtn.onClick.AddListener(() =>
        {
            ShowPaymentDetailsPopup(false);
        });
        cancelBankDetailsBtn.onClick.AddListener(HidePaymentDetailsPopup);
        cancelUpiDetailsBtn.onClick.AddListener(HidePaymentDetailsPopup);
        withdrawBtn.onClick.AddListener(SubmitWithdrawRequest);
        addUpiDetailsBtn.onClick.AddListener(AddUpiDetails);
        addBankDetailsBtn.onClick.AddListener(AddBankDetails);
        bankNameIF.OnValueChanged.AddListener((string val) => OnBankDetailsEnter());
        accountHolderNameIF.OnValueChanged.AddListener((string val) => OnBankDetailsEnter());
        accountNumberIF.OnValueChanged.AddListener((string val) => OnBankDetailsEnter());
        ifscCodeIF.OnValueChanged.AddListener((string val) => OnBankDetailsEnter());
        upiBankNameIF.OnValueChanged.AddListener((string val) => OnUpiDetailsEnter());
        upiIdIF.OnValueChanged.AddListener((string val) => OnUpiDetailsEnter());
        amountIF.OnValueChanged.AddListener((string val) =>
        {
            if (int.TryParse(val, out int amount))
            {
                amountToWithdraw = amount;
            }
            else
            {
                amountToWithdraw = 0;
            }
        });
    }

    private void OnDestroy()
    {
        GameManager.Instance.OnWalletUpdated -= UpdateWalletAmount;
    }

    private void OnEnable()
    {
        UpdateWalletAmount(GameManager.Instance.WalletAmount);
        HidePaymentDetailsPopup();
        if(details.Count <= 0)
        {
            withdrawBtn.interactable = false;
        }
    }

    private void ShowPaymentDetailsPopup(bool showBankDetails = true)
    {
        bankAndUpiDetailPopup.SetActive(true);
        if(showBankDetails)
        {
            bankDetailsObj.SetActive(true);
            upiDetailsObj.SetActive(false);
            bankNameIF.Text = "";
            accountHolderNameIF.Text = "";
            accountNumberIF.Text = "";
            ifscCodeIF.Text = "";
            addBankDetailsBtn.interactable = false;
        }
        else
        {
            bankDetailsObj.SetActive(false);
            upiDetailsObj.SetActive(true);
            upiBankNameIF.Text = "";
            upiIdIF.Text = "";
            addUpiDetailsBtn.interactable = false; 
        }
    }

    private void OnBankDetailsEnter()
    {
        if (!string.IsNullOrEmpty(bankNameIF.Text) &&
           !string.IsNullOrEmpty(accountHolderNameIF.Text) &&
           !string.IsNullOrEmpty(accountNumberIF.Text) &&
           !string.IsNullOrEmpty(ifscCodeIF.Text))
        {
            addBankDetailsBtn.interactable = true;
        }
        else
        {
            addBankDetailsBtn.interactable = false;
        }
    }

    private void OnUpiDetailsEnter()
    {
        if (!string.IsNullOrEmpty(upiBankNameIF.Text) &&
           !string.IsNullOrEmpty(upiIdIF.Text))
        {
            addUpiDetailsBtn.interactable = true;
        }
        else
        {
            addUpiDetailsBtn.interactable = false;
        }
    }

    private void AddBankDetails()
    {
        AndroidToast.Show("Bank Added Successfully");
        HidePaymentDetailsPopup();

        // Create a PaymentDetailsData object with the required information
        PaymentDetailsData data = new PaymentDetailsData
        {
            id = paymentDetailIdCounter++,
            paymentType = PaymentType.Bank,
            BankName = bankNameIF.Text,
            BankAccountNumber = accountNumberIF.Text,
            AccountHolderName = accountHolderNameIF.Text,
            IfscCode = ifscCodeIF.Text,
        };

        InstantiatePaymentObj(data, details.Count);
    }

    private void AddUpiDetails()
    {
        AndroidToast.Show("UPI Added Successfully");
        HidePaymentDetailsPopup();

        // Create a PaymentDetailsData object with the required information
        PaymentDetailsData data = new PaymentDetailsData
        {
            id = paymentDetailIdCounter++,
            paymentType = PaymentType.UPI,
            BankName = upiBankNameIF.Text,
            upiId = upiIdIF.Text,
        };

       InstantiatePaymentObj(data, details.Count);
    }

    private void InstantiatePaymentObj(PaymentDetailsData data, int id)
    {
        // Instantiate the prefab and get the PaymentDetails component
        GameObject paymentDetailsGO = Instantiate(userpaymentDetailsPrefab, paymentDetailsObj.transform);
        PaymentDetails paymentDetails = paymentDetailsGO.GetComponent<PaymentDetails>();
        paymentDetails.setPaymentDetailsData(data);

        details.Add(paymentDetails);
        withdrawBtn.interactable = true;

        if (details.Count == 1)
        {
            paymentDetails.selectedGlowObj.SetActive(true);
            selectedPayment = data;
        }
        else if(details.Count >= 3)
        {
            addBankAccountBtn.interactable = false;
            addUPIBtn.interactable = false;
        }
        LayoutRebuilder.ForceRebuildLayoutImmediate(paymentDetailsObj.GetComponent<RectTransform>());
    }

    private void HidePaymentDetailsPopup()
    {
        bankAndUpiDetailPopup.SetActive(false);
    }

    private void SubmitWithdrawRequest()
    {
        AndroidToast.Show($"Withdraw Request of ₹ {amountToWithdraw} Submitted");
    }

    private void UpdateWalletAmount(float amount)
    {
        balanceAmountText.text = $"₹{amount:F2}";
    }

    public void SetSelectedPaymentDetail(int id)
    {
       details.ForEach(detail =>
        {
            if (detail.GetId() == id)
            {
                selectedPayment = detail.GetPaymentDetailsData();
            }
            else
            {
                detail.SetSelectedState(false);
            }
        });

    }

    public void RemoveUserAccountDetail(int id)
    {
        int index = details.FindIndex(d => d.GetId() == id);

        if (index == -1)
        {
            Debug.LogError($"Account id {id} not found");
            return;
        }

        PaymentDetails item = details[index];

        details.RemoveAt(index);
        Destroy(item.gameObject);

        if(details.Count == 0)
        {
            withdrawBtn.interactable = false;
            paymentDetailIdCounter = 1;
        }
        else
        {
            // If the removed item was selected, clear selection
            if (selectedPayment.id == item.GetPaymentDetailsData().id)
            {
                details[0].SetSelectedState(true);
            }
        }

        if(details.Count < 3)
        {
            addBankAccountBtn.interactable = true;
            addUPIBtn.interactable = true;
        }

        StartCoroutine(RebuildLayoutNextFrame());
    }

    private IEnumerator RebuildLayoutNextFrame()
    {
        yield return null; // wait one frame (Destroy completes)

        LayoutRebuilder.ForceRebuildLayoutImmediate(
            parentContentObj.GetComponent<RectTransform>()
        );
    }

}
