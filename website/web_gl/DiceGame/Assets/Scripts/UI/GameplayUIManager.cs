using TMPro;
using UnityEngine;
using UnityEngine.UI;
using DG.Tweening;
using System.Collections.Generic;
using System;
using System.Globalization;
using System.Linq;
using static GameApiClient;

public class GameplayUIManager : MonoBehaviour
{
    [Header("Text")]
    public TextMeshProUGUI balanceText;
    public TextMeshProUGUI gameStatusText;
    public TextMeshProUGUI winloseText;
    public TextMeshProUGUI diceResultText;
    public TextMeshProUGUI timerText;
    public TextMeshProUGUI insufficientBalance;
    public TextMeshProUGUI exposureAmountText;

    [Header("Buttons")]
    public Button[] diceNumbers;
    public Button[] moneyChips;
    public Button betResetBtn;
    public Button mainChipsButton;
    public Image[] diceNumImage;
    public Button userProfileBtn;
    [Tooltip("Top-left back button: returns to app home (Android) or site main page (WebGL). WebGL uses a larger invisible tap area.")]
    public Button backButton;

    [Header("Chip UI")]
    public Sprite chip50Sprite;
    public Sprite chip100Sprite;
    public Sprite chip500Sprite;
    public Sprite chip1000Sprite;
    public GameObject moneyChipsBG;
    public TextMeshProUGUI mainChipText;
    public Transform mainChipPos;
    public GameObject animateCoin;

    [Header("Results")]
    public TextMeshProUGUI[] lastRoundResults;
    public TextMeshProUGUI roundResultTitleText;

    [Header("Reactions")]
    public Image reactionEmoji;
    public List<Sprite> winEmojiesReaction;
    public List<Sprite> loseEmojiesReaction;

    [Header("Reconnect")]
    public GameObject reconnectPanel;
    public GameObject reconnectImageObj;
    public TextMeshProUGUI reconnectText;

    [Header("Alert")]
    public GameObject alertPopuo;
    public TextMeshProUGUI alertTitle;
    public TextMeshProUGUI alertText;

    private GameController gameController;

    private const string INSUFFICIENT_BALANCE_TTTLE = "INSUFFICIENT BALANCE";
    private const string INSUFFICIENT_BALANCE_DESC = "ADD AMOUNT TO YOUR WALLET TO PLACE BET.";
    private const string MAX_AMOUNT_TTTLE = "MAX LIMIT REACHED";
    private const string MAX_AMOUNT_DESC = "YOU HAVE PLACE BET OF MAXIMUM ALLOW LIMIT OF FOR EACH ROUND.";

    private float currentAmountValue = 50f;

    private bool chipsVisible;
    private readonly List<Vector2> chipsOriginalPos = new();
    private readonly List<float> availableChipAmounts = new() { 100f, 500f, 1000f };
    private Stack<BetCoin> betStack = new Stack<BetCoin>();
    private BetCoin[] betcoins = new BetCoin[6];
    private int maxAmountPerRound = -1;
    private List<TextMeshProUGUI> numberFrequency = new List<TextMeshProUGUI>();

    // Track current round status so button handler can decide between betting and prediction
    private RoundStatus currentStatus = RoundStatus.NONE;

    // Local ordered list of placed bets (chronological: index 0 = earliest)
    private readonly List<BetRecord> localOrderedBets = new List<BetRecord>();

    // cached last exposure value (from server) to allow local increment/decrement while waiting for server
    private float cachedExposure = 0f;

    private float netAmountChangeThisRound = 0f;

    // reconnect animation tween reference
    private Tween reconnectTween;

    /// <summary>WebGL-only larger invisible hit area for the back button (see <see cref="WebGLBackButtonHelper"/>).</summary>
    private Button _webglBackOverlayButton;

    private void Awake()
    {
        gameController = FindFirstObjectByType<GameController>();
        CacheChipPositions();
        for (int i = 0; i < diceNumImage.Length; i++)
        {
            diceNumImage[i].color = new Color32(255, 255, 255, 255);
        }
        lastRoundResults.ToList().ForEach(t => t.gameObject.SetActive(false));
        userProfileBtn.onClick.AddListener(ShowUserProfile);
        if (backButton != null)
        {
            _webglBackOverlayButton = WebGLBackButtonHelper.InstallLargeHitOverlayIfNeeded(backButton, BackToKotlin.GoBackToKotlin);
            if (_webglBackOverlayButton == null)
                backButton.onClick.AddListener(BackToKotlin.GoBackToKotlin);
        }

        // ensure reconnect UI is hidden initially
        if (reconnectPanel != null) reconnectPanel.SetActive(false);
        if (reconnectImageObj != null) reconnectImageObj.transform.localRotation = Quaternion.identity;
    }

    private void Start()
    {
        GameManager.Instance.OnWalletUpdated += UpdateBalance;
        numberFrequency = new List<TextMeshProUGUI>();
        SetMoneyChipBtnClick();
        SetFrequencyOfNumber();
        HideFrequencyOfNumber();

        // Hook reset button to call API to remove the most recent bet (undo)
        if (betResetBtn != null)
        {
            betResetBtn.onClick.AddListener(OnResetButtonClicked);
        }
    }

    private void OnDestroy()
    {
        GameManager.Instance.OnWalletUpdated -= UpdateBalance;

        if (betResetBtn != null)
        {
            betResetBtn.onClick.RemoveListener(OnResetButtonClicked);
        }
        if (_webglBackOverlayButton != null)
            _webglBackOverlayButton.onClick.RemoveListener(BackToKotlin.GoBackToKotlin);
        else if (backButton != null)
            backButton.onClick.RemoveListener(BackToKotlin.GoBackToKotlin);

        // stop any running reconnect animation
        StopReconnectAnimation();
    }

    #region Reconnect UI

    // Show or hide the reconnect panel.
    // When showing, set text to "Reconnecting" and start rotation animation:
    // 0 -> -360 -> 0 (looping).
    public void ShowReconnectPanel(bool show)
    {
        if (reconnectPanel == null) return;

        reconnectPanel.SetActive(show);

        if (show)
        {
            if (reconnectText != null)
                reconnectText.text = "Reconnecting";

            StartReconnectAnimation();
        }
        else
        {
            StopReconnectAnimation();
        }
    }

    private void StartReconnectAnimation()
    {
        if (reconnectImageObj == null) return;

        // stop previous tween if any
        reconnectTween?.Kill();

        // Ensure starting rotation is zero
        reconnectImageObj.transform.localRotation = Quaternion.identity;

        // Rotate to -360 then back to 0 using Yoyo loop so it goes 0 -> -360 -> 0 repeatedly
        reconnectTween = reconnectImageObj.transform
            .DOLocalRotate(new Vector3(0f, 0f, -360f), 0.9f, RotateMode.Fast)
            .SetEase(Ease.Linear)
            .SetLoops(-1, LoopType.Yoyo);
    }

    private void StopReconnectAnimation()
    {
        if (reconnectImageObj != null)
        {
            reconnectTween?.Kill();
            reconnectTween = null;
            reconnectImageObj.transform.localRotation = Quaternion.identity;
        }
    }

    #endregion

    #region UI Setup

    public void SetGameUI(RoundStatus status, float balanceAmount, int[] lastResults, bool isCurrentRound,
        BetAmountSummary[] betAmountSummary,int maxAmountPerRound)
    {
        // store current status for click-time decisions
        currentStatus = status;
        this.maxAmountPerRound = maxAmountPerRound;

        UpdateBalance(balanceAmount);
        SetGameStatusText(status);
        SetBettingButtons(status);

        winloseText.gameObject.SetActive(false);
        diceResultText.gameObject.SetActive(false);
        reactionEmoji.gameObject.SetActive(false);
        insufficientBalance.gameObject.SetActive(false);

        chipsVisible = true;
        ShowHideChips();

        SetMoneyChipBtnClick();
        UpdateRoundResults(lastResults, isCurrentRound);

        // sync bets for the current round and render UI
        FetchAndRenderCurrentRoundBets();

        // fetch and show exposure for current user (or overall) when setting up UI
        FetchAndUpdateExposure();
    }

    public void UpdateGameUI(RoundStatus status, float balanceAmount, BetAmountSummary[] summaries)
    {
        // store current status for click-time decisions
        currentStatus = status;

        UpdateBalance(balanceAmount);
        SetGameStatusText(status);
        SetBettingButtons(status);

        // refresh exposure when UI updates
        FetchAndUpdateExposure();
    }

    #endregion

    #region Status / Buttons

    private void SetGameStatusText(RoundStatus status)
    {
        gameStatusText.text = status switch
        {
            RoundStatus.WAITING => "Waiting for next round...",
            RoundStatus.BETTING => "Place your bets",
            RoundStatus.CLOSED => "Betting Closed",
            RoundStatus.RESULT or RoundStatus.COMPLETED => "Round Completed",
            _ => ""
        };
    }

    private void ShowUserProfile()
    {
        UIManager.Instance.ShowPanel(UIPanelType.UserProfile);
    }

    private void SetBettingButtons(RoundStatus status)
    {
        bool canBet = status == RoundStatus.BETTING;

        // Instead of disabling dice buttons, change their visual appearance.
        // Leave them interactable so we can capture clicks and send prediction when betting is closed.
        for (int i = 0; i < diceNumbers.Length; i++)
        {
            // ensure button remains clickable for prediction flow
            if (diceNumbers[i] != null)
            {
                // ensure onClick handler is attached only once
                diceNumbers[i].onClick.RemoveAllListeners();
                int number = i + 1;
                diceNumbers[i].onClick.AddListener(() => DiceNumberButton(number));
            }

            if (diceNumbers != null && i < diceNumbers.Length && diceNumbers[i] != null)
            {
                // Active look when betting allowed, dimmed when not
                diceNumbers[i].GetComponent<Image>().color = canBet
                    ? new Color32(255, 255, 255, 255) // normal
                    : new Color32(150, 150, 150, 200); // dimmed / greyed
            }
        }

        // Keep other controls disabled when betting not allowed
        mainChipsButton.interactable = canBet;
        if (betResetBtn != null)
            betResetBtn.interactable = canBet;

        if (chipsVisible && !canBet)
        {
            ShowHideChips();
        }
    }

    #endregion

    #region Dice Betting

    public void DiceNumberButton(int number)
    {
        // If betting is allowed, proceed with normal bet placement
        if (currentStatus == RoundStatus.BETTING)
        {
            if (GameManager.Instance.WalletAmount < currentAmountValue)
            {
                ShowPopup(INSUFFICIENT_BALANCE_TTTLE, INSUFFICIENT_BALANCE_DESC);
                return;
            }
            if (maxAmountPerRound > 0 && cachedExposure + currentAmountValue > maxAmountPerRound)
            {
                ShowPopup(MAX_AMOUNT_TTTLE, MAX_AMOUNT_DESC);
                return;
            }

            gameController.PlaceBet(number, currentAmountValue, (success) =>
            {
                if (!success) return;

                // Animate ephemeral coin and then apply to persistent coin or create persistent coin if first bet
                AnimateAndApplyBet(
                    mainChipPos.position,
                    number,
                    currentAmountValue
                );

                // Add to local ordered list (assume current time)
                localOrderedBets.Add(new BetRecord
                {
                    number = number,
                    amount = currentAmountValue,
                    created_at = DateTime.UtcNow
                });

                // locally increment exposure immediately for snappy UI
                cachedExposure += currentAmountValue;
                UpdateExposureText(cachedExposure);

                // fetch authoritative exposure from server (best-effort)
                FetchAndUpdateExposure();

                AudioManager.Instance.PlaySfx(SfxType.CoinSfx);
            });

            return;
        }

        // If betting is closed (or any non-betting status), submit a prediction instead.
        var api = GameManager.Instance?.ApiClient;
        if (api == null)
        {
            Debug.LogWarning("SubmitPrediction: ApiClient not available");
            return;
        }

        // Predictions are free; send the selected number to the prediction API
        api.SubmitPrediction(number, (ok, resp, err) =>
        {
            if (ok && resp != null)
            {
                Debug.Log($"Prediction submitted: {resp.message}");
                // Optionally provide UI feedback (toast/popup) here
            }
            else
            {
                Debug.LogWarning("SubmitPrediction failed: " + err);
            }
        });
    }

    #endregion

    #region Chips

    public void ShowHideChips()
    {
        if (chipsVisible)
        {
            for (int i = 0; i < moneyChips.Length; i++)
            {
                RectTransform chip = moneyChips[i].GetComponent<RectTransform>();
                chip.DOMove(mainChipPos.position, 0.3f).SetEase(Ease.InBack).OnComplete(() => chip.gameObject.SetActive(false));
            }
            for (int i = 0; i < diceNumImage.Length; i++)
            {
                diceNumImage[i].color = new Color32(255, 255, 255, 255);
            }
            moneyChipsBG.SetActive(false);
            chipsVisible = false;
        }
        else
        {
            moneyChipsBG.SetActive(true);
            for (int i = 0; i < moneyChips.Length; i++)
            {
                RectTransform chip = moneyChips[i].GetComponent<RectTransform>();
                chip.gameObject.SetActive(true);
                chip.position = mainChipPos.position;
                chip.DOMove(chipsOriginalPos[i], 0.35f).SetEase(Ease.OutBack);
            }
            for (int i = 0; i < diceNumImage.Length; i++)
            {
                diceNumImage[i].color = new Color32(0, 0, 0, 128);
            }
            chipsVisible = true;
        }
        AudioManager.Instance.PlaySfx(SfxType.CoinSfx);
        mainChipText.text = $"{currentAmountValue}";
    }

    private void CacheChipPositions()
    {
        chipsOriginalPos.Clear();

        foreach (var chip in moneyChips)
        {
            chipsOriginalPos.Add(chip.transform.position);
        }
    }

    private void SetMoneyChipBtnClick()
    {
        mainChipPos.GetComponent<Image>().sprite = currentAmountValue switch
        {
            50f => chip50Sprite,
            100f => chip100Sprite,
            500f => chip500Sprite,
            1000f => chip1000Sprite,
            _ => null
        };
        availableChipAmounts.Sort();

        for (int i = 0; i < moneyChips.Length; i++)
        {
            float amount = availableChipAmounts[i];
            Button btn = moneyChips[i];

            btn.onClick.RemoveAllListeners();
            btn.onClick.AddListener(() => SetCurrentChipAmount(amount));

            btn.transform.GetChild(0).GetComponent<TextMeshProUGUI>().text = amount.ToString();
            btn.GetComponent<Image>().sprite = amount switch
            {
                50f => chip50Sprite,
                100f => chip100Sprite,
                500f => chip500Sprite,
                1000f => chip1000Sprite,
                _ => null
            };
        }
    }

    private void SetCurrentChipAmount(float amount)
    {
        availableChipAmounts.Remove(amount);
        availableChipAmounts.Add(currentAmountValue);
        currentAmountValue = amount;

        ShowHideChips();
        SetMoneyChipBtnClick();
    }

    #endregion

    #region Results / Feedback

    public void UpdateBalance(float amount)
    {
        balanceText.text = $"₹{amount}";
    }

    public void UpdateTimer(int timeInSeconds)
    {
        timerText.text = timeInSeconds.ToString();
    }

    public void UpdateFrequencyOfNum(List<Tuple<int, int>> winningNum)
    {
        diceResultText.gameObject.SetActive(true);
        diceResultText.text = "Dice Rolled: ";
        int count = 0;
        HideFrequencyOfNumber();
        winningNum.ForEach(res =>
        {
            int value = res.Item1;
            int frequency = res.Item2;
            if (count > 0)
                diceResultText.text += ",";
            diceResultText.text += $"{value}({frequency})";
            numberFrequency[value - 1].text = $"x{frequency}";
            numberFrequency[value - 1].gameObject.SetActive(true);
            count++;
        });
    }

    public void UpdateWinLoseText(float amount)
    {
        winloseText.gameObject.SetActive(true);
        netAmountChangeThisRound = amount;

        bool isWin = amount >= 0;
        winloseText.text = isWin
            ? $"You Won ₹{amount}"
            : $"You Lose ₹{Mathf.Abs(amount)}";

        winloseText.color = isWin ? Color.green : Color.red;
        reactionEmoji.sprite = GetReactionEmoji(isWin);
        //reactionEmoji.gameObject.SetActive(true);
    }

    public void ShowHideWinLoseText()
    {
        if (netAmountChangeThisRound > 0)
            winloseText.gameObject.SetActive(true);
        else
            winloseText.gameObject.SetActive(false);
    }

    public void UpdateRoundResults(int[] results, bool isCurrentRoundResult = false)
    {
        if(isCurrentRoundResult)
        {
            roundResultTitleText.text = "";
        }
        else
        {
            roundResultTitleText.text = "Last Round Results";
        }
        for (int i = 0; i < lastRoundResults.Length; i++)
        {
            lastRoundResults[i].text = i < results.Length ? results[i].ToString() : "-";
            lastRoundResults[i].gameObject.SetActive(i < results.Length);
        }
    }

    public void HideFrequencyOfNumber()
    {
        numberFrequency.ToList().ForEach(t => t.gameObject.SetActive(false));
    }

    #endregion

    #region Helpers

    private Sprite GetReactionEmoji(bool isWin)
    {
        var list = isWin ? winEmojiesReaction : loseEmojiesReaction;
        return list[UnityEngine.Random.Range(0, list.Count)];
    }

    public void ShowPopup(string title, string message)
    {
        if (alertPopuo == null || alertTitle == null || alertText == null) return;
        alertTitle.text = title;
        alertText.text = message;
        alertPopuo.SetActive(true);
    }

    // New: animate an ephemeral coin and apply the bet to the persistent coin for the number.
    private void AnimateAndApplyBet(Vector3 startPos, int diceNumber, float amount)
    {
        int index = Mathf.Clamp(diceNumber - 1, 0, diceNumbers.Length - 1);
        Transform target = diceNumbers[index].transform;

        // Create ephemeral coin for animation
        GameObject epCoin = Instantiate(animateCoin, transform);
        epCoin.SetActive(true);

        epCoin.transform.GetChild(0)
            .GetComponent<TextMeshProUGUI>().text = amount.ToString("F0");

        var img = epCoin.GetComponent<Image>();
        if (img != null)
            img.sprite = GetSpriteForChipAmount(amount);

        RectTransform rt = epCoin.GetComponent<RectTransform>();
        rt.position = startPos;
        rt.localScale = Vector3.one;

        Sequence seq = DOTween.Sequence();

        seq.Append(
           rt.DOMove(target.position, 0.2f)
             .SetEase(Ease.InQuad)
        );

        seq.OnComplete(() =>
        {
            // If there is no persistent coin for this number -> convert ephemeral into persistent
            if (betcoins[index] == null)
            {
                // parent and make persistent
                epCoin.transform.SetParent(target, worldPositionStays: false);

                var persistentText = epCoin.transform.GetChild(0).GetComponent<TextMeshProUGUI>();

                betcoins[index] = new BetCoin
                {
                    coinObj = epCoin,
                    amountText = persistentText,
                    diceNumber = diceNumber,
                    amount = amount
                };

                RectTransform prt = epCoin.GetComponent<RectTransform>();
                if (prt != null)
                {
                    prt.anchoredPosition = Vector2.zero;
                    prt.localScale = Vector3.one * 0.65f;
                }

                // push a delta entry so undo can subtract this amount
                betStack.Push(new BetCoin
                {
                    coinObj = betcoins[index].coinObj,
                    amountText = betcoins[index].amountText,
                    diceNumber = diceNumber,
                    amount = amount
                });
            }
            else
            {
                // Update existing persistent coin: increment amount and refresh visuals.
                float prev = betcoins[index].amount;
                float total = prev + amount;
                betcoins[index].amount = total;

                if (betcoins[index].amountText != null)
                    betcoins[index].amountText.text = total.ToString("F0");

                var imgPersistent = betcoins[index].coinObj.GetComponent<Image>();
                if (imgPersistent != null)
                    imgPersistent.sprite = GetSpriteForChipAmount(total);

                // small punch animation to indicate update
                RectTransform prt = betcoins[index].coinObj.GetComponent<RectTransform>();
                if (prt != null)
                    prt.DOPunchScale(Vector3.one * 0.12f, 0.15f, 1, 0.25f);

                // destroy ephemeral coin used for animation
                Destroy(epCoin);

                // push a delta entry onto stack to allow undoing this increment
                betStack.Push(new BetCoin
                {
                    coinObj = betcoins[index].coinObj,
                    amountText = betcoins[index].amountText,
                    diceNumber = diceNumber,
                    amount = amount
                });
            }
        });
    }

    private Sprite GetSpriteForChipAmount(float amount)
    {
        // thresholds requested by product:
        // <100 => 50
        // 100..499 => 100
        // 500..999 => 500
        // >=1000 => 1000
        if (amount < 100f) return chip50Sprite;
        if (amount < 500f) return chip100Sprite;
        if (amount < 1000f) return chip500Sprite;
        return chip1000Sprite;
    }

    public void RemoveLastBet()
    {
        if (betStack.Count == 0) return;

        BetCoin lastBet = betStack.Pop();

        if (lastBet == null || lastBet.coinObj == null)
        {
            // nothing visual to do
            UpdateBalance(GameManager.Instance.WalletAmount);
            return;
        }

        // find index by diceNumber
        int idx = Mathf.Clamp(lastBet.diceNumber - 1, 0, betcoins.Length - 1);

        if (betcoins[idx] == null)
        {
            // persistent coin missing — just destroy if any and refresh
            if (lastBet.coinObj != null)
                Destroy(lastBet.coinObj);

            UpdateBalance(GameManager.Instance.WalletAmount);
            return;
        }

        // decrement persistent amount by delta stored in stack entry
        betcoins[idx].amount -= lastBet.amount;

        if (betcoins[idx].amount <= 0f)
        {
            // remove persistent coin
            if (betcoins[idx].coinObj != null)
                Destroy(betcoins[idx].coinObj);
            betcoins[idx] = null;
        }
        else
        {
            // update displayed amount and sprite
            if (betcoins[idx].amountText != null)
                betcoins[idx].amountText.text = betcoins[idx].amount.ToString("F0");

            var img = betcoins[idx].coinObj.GetComponent<Image>();
            if (img != null)
                img.sprite = GetSpriteForChipAmount(betcoins[idx].amount);

            // small feedback
            var rt = betcoins[idx].coinObj.GetComponent<RectTransform>();
            if (rt != null)
                rt.DOPunchScale(Vector3.one * 0.08f, 0.12f, 1, 0.2f);
        }

        // Update balance display
        UpdateBalance(GameManager.Instance.WalletAmount);
    }

    public void RemoveAllBets()
    {
        while (betStack.Count > 0)
        {
            betStack.Pop();
        }

        for (int i = 0; i < betcoins.Length; i++)
        {
            if (betcoins[i] != null && betcoins[i].coinObj != null)
                Destroy(betcoins[i].coinObj);
            betcoins[i] = null;
        }
    }

    #endregion

    #region New: Reset button -> DeleteLastBet API

    private void OnResetButtonClicked()
    {
        // Prevent repeated clicks
        if (betResetBtn != null)
            betResetBtn.interactable = false;

        var api = GameManager.Instance?.ApiClient;
        if (api == null)
        {
            Debug.LogWarning("DeleteLastBet: ApiClient not available");
            if (betResetBtn != null) betResetBtn.interactable = true;
            return;
        }

        // Call server to remove user's most recent bet
        api.DeleteLastBet((ok, err) =>
        {
            if (ok)
            {
                // Refresh authoritative state from server (bets & exposure & wallet)
                GameManager.Instance.RefreshWallet();
                FetchAndRenderCurrentRoundBets();
                FetchAndUpdateExposure();
            }
            else
            {
                Debug.LogWarning("DeleteLastBet failed: " + err);
                // On failure, try to refresh wallet to keep UI consistent
                GameManager.Instance.RefreshWallet();
            }

            if (betResetBtn != null)
                betResetBtn.interactable = true;
        });
    }

    #endregion

    #region Round Bets sync & rendering

    // Lightweight record to hold number, amount and created time
    private class BetRecord
    {
        public int number;
        public float amount;
        public DateTime created_at;
    }

    private void FetchAndRenderCurrentRoundBets()
    {
        var api = GameManager.Instance?.ApiClient;
        if (api == null) return;

        Debug.Log("Fetching current round bets from server...");
        // First get current round to obtain round_id
        api.GetCurrentRound((ok, data, err) =>
        {
            if (!ok || data == null)
            {
                Debug.LogWarning("FetchAndRenderCurrentRoundBets: Failed to get current round - " + err);
                return;
            }

            string currentRoundId = data.RoundId;
            if (string.IsNullOrEmpty(currentRoundId)) return;

            // Fetch round bets for this round id
            api.GetRoundBets(currentRoundId, (okB, resp, errB) =>
            {
                if (!okB || resp == null)
                {
                    Debug.LogWarning("FetchAndRenderCurrentRoundBets: Failed to get current round - " + errB);
                    return;
                }

                // If there are individual bets, map to localOrderedBets and render
                if (resp.individual_bets != null)
                {
                    // clear existing
                    localOrderedBets.Clear();

                    foreach (var b in resp.individual_bets)
                    {
                        // parse amount safely
                        if (!float.TryParse(b.chip_amount, NumberStyles.Any, CultureInfo.InvariantCulture, out float amt))
                            amt = 0f;

                        DateTime created = DateTime.UtcNow;
                        if (!string.IsNullOrEmpty(b.created_at))
                        {
                            // attempt parse ISO timestamp
                            if (!DateTime.TryParse(b.created_at, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out created))
                            {
                                created = DateTime.UtcNow;
                            }
                        }

                        localOrderedBets.Add(new BetRecord
                        {
                            number = b.number,
                            amount = amt,
                            created_at = created
                        });
                    }

                    // order ascending to guarantee chronological order
                    localOrderedBets.Sort((x, y) => DateTime.Compare(x.created_at, y.created_at));

                    // Render bets according to ordered list (aggregated by number)
                    RenderBetsFromLocalList();

                    // update cached exposure from local list as baseline, then fetch authoritative server exposure
                    cachedExposure = 0f;
                    foreach (var r in localOrderedBets) cachedExposure += r.amount;
                    UpdateExposureText(cachedExposure);

                    // fetch authoritative exposure from server
                    FetchAndUpdateExposure();
                }
            });
        });
    }

    private void RenderBetsFromLocalList()
    {
        // Clear existing visuals and local stack: server authoritative snapshot replaces client undo history
        RemoveAllBets();

        // Aggregate sums per number
        var sums = new Dictionary<int, float>();

        foreach (var r in localOrderedBets)
        {
            int num = Mathf.Clamp(r.number, 1, diceNumbers.Length);
            if (!sums.ContainsKey(num)) sums[num] = 0f;
            sums[num] += r.amount;
        }

        // For each number that has a sum, create a single persistent coin
        foreach (var kvp in sums)
        {
            int number = kvp.Key;
            float total = kvp.Value;

            int index = number - 1;
            Transform target = diceNumbers[index].transform;

            GameObject coin = Instantiate(animateCoin, transform);
            coin.SetActive(true);

            var text = coin.transform.GetChild(0).GetComponent<TextMeshProUGUI>();
            if (text != null)
                text.text = total.ToString("F0");

            var img = coin.GetComponent<Image>();
            if (img != null)
                img.sprite = GetSpriteForChipAmount(total);

            coin.transform.SetParent(target, worldPositionStays: false);

            RectTransform rt = coin.GetComponent<RectTransform>();
            if (rt != null)
            {
                rt.anchoredPosition = Vector2.zero;
                rt.localScale = Vector3.one * 0.65f;
            }

            BetCoin bc = new BetCoin
            {
                coinObj = coin,
                amountText = text,
                diceNumber = number,
                amount = total
            };

            betcoins[index] = bc;

            // Note: we do not push historical per-bet entries onto betStack here.
            // Undo (DeleteLastBet) should be performed via server and then we re-sync by fetching bets again.
        }
    }

    #endregion

    #region Exposure fetch & UI helpers

    private void FetchAndUpdateExposure()
    {
        var api = GameManager.Instance?.ApiClient;
        if (api == null) return;

        // get current round id first
        api.GetCurrentRound((ok, data, err) =>
        {
            if (!ok || data == null) return;
            string roundId = data.RoundId;

            // attempt to obtain user id via reflection from GameManager (if present)
            int? userId = TryGetGameManagerUserId();

            api.GetRoundExposure(roundId, userId, (okE, resp, errE) =>
            {
                if (!okE || resp == null) return;

                // If API returned an exposure list, pick appropriate entry:
                // prefer the single entry (if userId was requested) or match by player_id/username.
                float value = 0f;
                if (resp.exposure != null && resp.exposure.Count > 0)
                {
                    ExposureEntry match = null;

                    if (userId.HasValue)
                    {
                        // try find by player_id
                        match = resp.exposure.Find(x => x.player_id == userId.Value);
                        if (match == null && resp.exposure.Count == 1)
                            match = resp.exposure[0];
                    }
                    else
                    {
                        // attempt match by username if available from GameManager
                        string username = TryGetGameManagerUsername();
                        if (!string.IsNullOrEmpty(username))
                            match = resp.exposure.Find(x => string.Equals(x.username, username, StringComparison.OrdinalIgnoreCase));

                        if (match == null && resp.exposure.Count == 1)
                            match = resp.exposure[0];
                    }

                    // fallback: if no match, try to find entry for this client by heuristics
                    if (match == null)
                    {
                        // try to find exposure entry where username equals wallet/username etc.
                        string username = TryGetGameManagerUsername();
                        if (!string.IsNullOrEmpty(username))
                            match = resp.exposure.Find(x => string.Equals(x.username, username, StringComparison.OrdinalIgnoreCase));
                    }

                    if (match != null)
                    {
                        if (!float.TryParse(match.exposure_amount, NumberStyles.Any, CultureInfo.InvariantCulture, out value))
                            value = 0f;
                    }
                    else
                    {
                        // if still not found, set to 0
                        value = 0f;
                    }
                }

                // update cached exposure and UI
                cachedExposure = value;
                UpdateExposureText(cachedExposure);
            });
        });
    }

    private int? TryGetGameManagerUserId()
    {
        try
        {
            var gm = GameManager.Instance;
            if (gm == null) return null;

            var t = gm.GetType();
            // common property names
            var prop = t.GetProperty("UserId") ?? t.GetProperty("PlayerId") ?? t.GetProperty("userId") ?? t.GetProperty("playerId");
            if (prop != null)
            {
                var v = prop.GetValue(gm);
                if (v is int vi) return vi;
                if (v is long vl) return (int)vl;
                if (v is string vs && int.TryParse(vs, out int parsed)) return parsed;
            }
        }
        catch { }
        return null;
    }

    private string TryGetGameManagerUsername()
    {
        try
        {
            var gm = GameManager.Instance;
            if (gm == null) return null;

            var t = gm.GetType();
            var prop = t.GetProperty("Username") ?? t.GetProperty("username") ?? t.GetProperty("UserName") ?? t.GetProperty("userName");
            if (prop != null)
            {
                var v = prop.GetValue(gm);
                if (v != null) return v.ToString();
            }
        }
        catch { }
        return null;
    }

    private void UpdateExposureText(float amount)
    {
        if (exposureAmountText == null) return;
        // keep the format requested by product: "{amount} of text"
        exposureAmountText.text = $"EXP: ₹{amount:F2}";
    }

    private void SetFrequencyOfNumber()
    {
        foreach(var number in diceNumbers)
        {
            numberFrequency.Add(number.transform.GetChild(1).GetComponent<TextMeshProUGUI>());
        }
    }
    #endregion
}

[System.Serializable]
public class BetCoin
{
    public GameObject coinObj;
    public TextMeshProUGUI amountText;
    public int diceNumber;
    public float amount;

    public void changeAmount(float newAmount)
    {
        amount = newAmount;
        amountText.text = newAmount.ToString();
    }
}