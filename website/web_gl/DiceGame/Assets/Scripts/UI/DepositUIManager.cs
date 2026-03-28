using AdvancedInputFieldPlugin;
using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using static GameApiClient;

public enum PaymentMethodType
{
    GPay,
    PhonePe,
    Paytm,
    UPI,
    BANK
}

public class DepositUIManager : MonoBehaviour
{
    public TextMeshProUGUI balanceAmountText;
    public GameObject amountAndVerificationUI;
    public GameObject paymentUI;

    [Header("Amount")]
    public AdvancedInputField amount;
    public Button proceedToPayBtn;

    [Header("Transaction UTR")]
    public AdvancedInputField enterAmountInput;
    public TextMeshProUGUI ssFileNameText;
    public Button uploadTranscationSSBtn;
    public Button submitTranscationSSBtn;

    [Header("UPI Payment")]
    public Button gpayBtn;
    public Button phonepeBtn;
    public Button paytmBtn;
    public Button upiBtn;
    public Button copyUpiIdBtn;
    public TextMeshProUGUI upiIdText;

    [Header("Bank Details")]
    public GameObject bankDetailsParentObj;
    public TextMeshProUGUI accountHolderText;
    public TextMeshProUGUI accountNumberText;
    public TextMeshProUGUI ifscCodeText;
    public TextMeshProUGUI bankNameText;

    [Header("Alert Popup")]
    public GameObject alertPopup;
    public TextMeshProUGUI descriptionText;
    public Button okayBtn;

    private int enterAmount = 0;
    private string uploadedImagePath;
    private byte[] uploadedImageBytes;
    private string uploadedImageFileName;

    private PaymentMethod phonepe;
    private PaymentMethod gpay;
    private PaymentMethod paytm;
    private PaymentMethod upi;
    private PaymentMethod bank;

    private void Start()
    {
        GameManager.Instance.OnWalletUpdated += UpdateWalletAmount;
        proceedToPayBtn.onClick.AddListener(() =>
        {
            ProceedToPay();
        });
        uploadTranscationSSBtn.onClick.AddListener(() =>
        {
            UploadTranscationSS();
        });
        submitTranscationSSBtn.onClick.AddListener(() =>
        {
            SubmitDepositRequest();
        });
        gpayBtn.onClick.AddListener(() =>
        {
            OpenPaymentApp(PaymentMethodType.GPay);
        });
        phonepeBtn.onClick.AddListener(() =>
        {
            OpenPaymentApp(PaymentMethodType.PhonePe);
        });
        paytmBtn.onClick.AddListener(() =>
        {
            OpenPaymentApp(PaymentMethodType.Paytm);
        });
        upiBtn.onClick.AddListener(() =>
        {
            OpenPaymentApp(PaymentMethodType.UPI);
        });
        enterAmountInput.OnValueChanged.AddListener((val) =>
        {
            if (string.IsNullOrEmpty(val))
            {
                enterAmount = 0;
                submitTranscationSSBtn.interactable = false;
            }
            else
            {
                enterAmount = int.Parse(val);
            }
            if (!string.IsNullOrEmpty(uploadedImageFileName) && enterAmount > 0)
            {
                submitTranscationSSBtn.interactable = true;
            }
        });
        amount.OnValueChanged.AddListener(OnAmountChange);
        ssFileNameText.gameObject.SetActive(false);
        submitTranscationSSBtn.interactable = false;
        alertPopup.gameObject.SetActive(false);
        okayBtn.onClick.AddListener(() =>
        {
            alertPopup.SetActive(false);
        });
    }

    private void OnEnable()
    {
        UpdateWalletAmount(GameManager.Instance.WalletAmount);
        amountAndVerificationUI.SetActive(true);
        paymentUI.SetActive(false);
    }

    private void ProceedToPay()
    {
        FetchPaymentMethodDetails();
        amountAndVerificationUI.SetActive(false);
        paymentUI.SetActive(true);
    }

    private void ShowAlertPopup(string description)
    {
        descriptionText.text = description;
        alertPopup.SetActive(true);
        okayBtn.onClick.RemoveAllListeners();
        okayBtn.onClick.AddListener(() =>
        {
            alertPopup.SetActive(false);
        });
    }

    private void FetchPaymentMethodDetails()
    {
        GameManager.Instance.ApiClient.GetPaymentMethods((success, methods, err) =>
        {
            if (success)
            {
                foreach (var method in methods)
                {
                    switch (method.method_type)
                    {
                        case PaymentMethodType.GPay:
                            gpay = method;
                            break;
                        case PaymentMethodType.PhonePe:
                            phonepe = method;
                            break;
                        case PaymentMethodType.Paytm:
                            paytm = method;
                            break;
                        case PaymentMethodType.UPI:
                            upi = method;
                            break;
                        case PaymentMethodType.BANK:
                            bank = method;
                            break;
                    }
                }
                if (bank == null) bankDetailsParentObj.SetActive(false);
                else
                {
                    bankDetailsParentObj.SetActive(true);
                    accountHolderText.text = bank.account_name;
                    accountNumberText.text = bank.account_number;
                    ifscCodeText.text = bank.ifsc_code;
                    bankNameText.text = bank.bank_name;
                }
                if (upi != null)
                {
                    upiIdText.text = upi.upi_id;
                    copyUpiIdBtn.onClick.RemoveAllListeners();
                    copyUpiIdBtn.onClick.AddListener(() =>
                    {
                        GUIUtility.systemCopyBuffer = upi.upi_id;
                        AndroidToast.Show("UPI ID Copied to Clipboard");
                    });
                }
                else
                {
                    upiIdText.gameObject.SetActive(false);
                    copyUpiIdBtn.gameObject.SetActive(false);
                }
            }
            else
            {
                Debug.LogError("Error fetching payment methods: " + err);
            }
        });
    }

    private void UploadTranscationSS()
    {
#if UNITY_ANDROID || UNITY_IOS
        NativeGallery.GetImageFromGallery(
            (path) =>
            {
                if (path != null)
                {
                    uploadedImagePath = path;
                    Debug.Log("Image selected: " + path);

                    // Optional: load preview
                    Texture2D texture = NativeGallery.LoadImageAtPath(path, 1024);
                    if (texture != null)
                    {
                        // Assign to UI RawImage if needed
                        // screenshotPreview.texture = texture;
                    }

                    // Now you can upload `File.ReadAllBytes(path)` to server
                    uploadedImageBytes = File.ReadAllBytes(path);
                    uploadedImageFileName = Path.GetFileName(path);
                    ssFileNameText.text = uploadedImageFileName;
                    ssFileNameText.gameObject.SetActive(true);
                    if (enterAmount > 0)
                        submitTranscationSSBtn.interactable = true;
                }
            },
            "Select Transaction Screenshot",
            "image/*"
        );
#else
    Debug.Log("Gallery picker only works on mobile.");
#endif
    }

    private void SubmitDepositRequest()
    {
        GameManager.Instance.ApiClient.UploadDepositProof(enterAmount.ToString(), uploadedImageBytes, uploadedImageFileName,
            callback: (success, response, err) =>
            {
                if (success)
                {
                    AndroidToast.Show("Request Submitted");
                    enterAmountInput.Text = "";
                    ssFileNameText.text = "";
                    ssFileNameText.gameObject.SetActive(false);
                    submitTranscationSSBtn.interactable = false;
                }
                else
                {
                    Debug.LogError("Error submitting deposit request: " + err);
                }
            });
    }

    private void OnAmountChange(string val)
    {
        if (string.IsNullOrEmpty(val))
        {
            enterAmount = 0;
        }
        else
        {
            enterAmount = int.Parse(val);
        }
    }

    private void OpenPaymentApp(PaymentMethodType method)
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        string upiId = "yourupi@bank";
        string payeeName = "Your App Name";
        string note = "WALLET TOPUP";
        string amountStr = enterAmount.ToString();

        string packageName = "";

        switch (method)
        {
            case PaymentMethodType.GPay:
                if (gpay == null)
                {
                    ShowAlertPopup("WE ARE FACING SOME ISSUE WITH GOOGLE PAY, PLEASE TRY ANOTHER ONE");
                    return;
                }
                packageName = "com.google.android.apps.nbu.paisa.user";
                upiId = gpay.upi_id;
                payeeName = gpay.name;
                break;
            case PaymentMethodType.PhonePe:
                if (phonepe == null)
                {
                    ShowAlertPopup("WE ARE FACING SOME ISSUE WITH PHONEPE, PLEASE TRY ANOTHER ONE");
                    return;
                }
                packageName = "com.phonepe.app";
                upiId = phonepe.upi_id;
                payeeName = phonepe.name;
                break;
            case PaymentMethodType.Paytm:
                if (paytm == null)
                {
                    ShowAlertPopup("WE ARE FACING SOME ISSUE WITH PAYTM, PLEASE TRY ANOTHER ONE");
                    return;
                }
                packageName = "net.one97.paytm";
                upiId = paytm.upi_id;
                payeeName = paytm.name;
                break;
            case PaymentMethodType.UPI:
                if (upi == null)
                {
                    ShowAlertPopup("WE ARE FACING SOME ISSUE WITH UPI, PLEASE TRY ANOTHER ONE");
                    return;
                }
                packageName = ""; // let system choose
                upiId = upi.upi_id;
                payeeName = upi.name;
                break;
        }

        string upiUrl =
            $"upi://pay?pa={upiId}&pn={payeeName}&am={amountStr}&cu=INR&tn={note}";

        try
        {
            using (AndroidJavaClass unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
            using (AndroidJavaObject activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity"))
            using (AndroidJavaObject intent = new AndroidJavaObject("android.content.Intent", "android.intent.action.VIEW"))
            using (AndroidJavaObject uri = new AndroidJavaClass("android.net.Uri")
                .CallStatic<AndroidJavaObject>("parse", upiUrl))
            {
                intent.Call<AndroidJavaObject>("setData", uri);

                if (!string.IsNullOrEmpty(packageName))
                    intent.Call<AndroidJavaObject>("setPackage", packageName);

                activity.Call("startActivity", intent);
            }
        }
        catch (System.Exception e)
        {
            ShowAlertPopup("APP FOUND. PLEASE INSTALL ONE TO PROCEED.");
            Debug.LogError("Payment app not found: " + e.Message);
        }
#else
        Debug.Log($"Opening payment app: {method} with amount {enterAmount}");
#endif
    }

    public void AmountChip(int chipAmount)
    {
        enterAmount += chipAmount;
        amount.Text = enterAmount.ToString();
    }

    private void UpdateWalletAmount(float amount)
    {
        balanceAmountText.text = $"₹{amount:F2}";
    }
}
