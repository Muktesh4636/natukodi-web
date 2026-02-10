using TMPro;
using UnityEngine;
using UnityEngine.UI;
using DG.Tweening;
using System.Collections.Generic;
using System;

public class GameplayUIManager : MonoBehaviour
{
    [Header("Text")]
    public TextMeshProUGUI balanceText;
    public TextMeshProUGUI gameStatusText;
    public TextMeshProUGUI winloseText;
    public TextMeshProUGUI diceResultText;
    public TextMeshProUGUI timerText;
    public TextMeshProUGUI insufficientBalance;

    [Header("Buttons")]
    public Button[] diceNumbers;
    public Button[] moneyChips;
    public Button betResetBtn;
    public Button mainChipsButton;
    public Image[] diceNumImage;
    public Button userProfileBtn;

    [Header("Chip UI")]
    public GameObject moneyChipsBG;
    public TextMeshProUGUI mainChipText;
    public Transform mainChipPos;
    public GameObject animateCoin;

    [Header("Results")]
    public TextMeshProUGUI[] lastRoundResults;

    [Header("Reactions")]
    public Image reactionEmoji;
    public List<Sprite> winEmojiesReaction;
    public List<Sprite> loseEmojiesReaction;

    private GameController gameController;

    private float currentAmountValue = 50f;

    private bool chipsVisible;
    private readonly List<Vector2> chipsOriginalPos = new();
    private readonly List<float> availableChipAmounts = new() { 100f, 500f, 1000f };
    private Stack<BetCoin> betStack = new Stack<BetCoin>();

    private void Awake()
    {
        gameController = FindFirstObjectByType<GameController>();
        CacheChipPositions();
        for (int i = 0; i < diceNumImage.Length; i++)
        {
            diceNumImage[i].color = new Color32(255, 255, 255, 255);
        }
        userProfileBtn.onClick.AddListener(ShowUserProfile);
    }

    private void Start()
    {
        GameManager.Instance.OnWalletUpdated += UpdateBalance;
    }

    private void OnDestroy()
    {
        GameManager.Instance.OnWalletUpdated -= UpdateBalance;
    }

    #region UI Setup

    public void SetGameUI(RoundStatus status, float balanceAmount, int[] lastResults)
    {
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
        UpdateLastRoundResults(lastResults);
    }

    public void UpdateGameUI(RoundStatus status, float balanceAmount)
    {
        UpdateBalance(balanceAmount);
        SetGameStatusText(status);
        SetBettingButtons(status);
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

        foreach (var btn in diceNumbers)
            btn.interactable = canBet;

        mainChipsButton.interactable = canBet;
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
        if (GameManager.Instance.WalletAmount < currentAmountValue)
        {
            ShowInsufficientBalance();
            return;
        }

        gameController.PlaceBet(number, currentAmountValue, (success) =>
        {
            if (!success) return;

            AnimateCoin(
                mainChipPos.position,
                number,
                currentAmountValue
            );
        });
    }

    public void ResetBet()
    {
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
        availableChipAmounts.Sort();

        for (int i = 0; i < moneyChips.Length; i++)
        {
            float amount = availableChipAmounts[i];
            Button btn = moneyChips[i];

            btn.onClick.RemoveAllListeners();
            btn.onClick.AddListener(() => SetCurrentChipAmount(amount));

            btn.interactable = GameManager.Instance.WalletAmount >= amount;
            btn.transform.GetChild(0).GetComponent<TextMeshProUGUI>().text = amount.ToString();
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

    public void UpdateRollDiceNum(List<Tuple<int,int>> winningNum)
    {
        diceResultText.gameObject.SetActive(true);
        diceResultText.text = "Dice Rolled: ";
        int count = 0;
        winningNum.ForEach(res =>
        {
            int value = res.Item1;
            int frequency = res.Item2;
            if(count > 0)
                diceResultText.text += ",";
            diceResultText.text += $"{value}({frequency})";
            count++;
        });
    }

    public void UpdateWinLoseText(float amount)
    {
        winloseText.gameObject.SetActive(true);

        bool isWin = amount >= 0;
        winloseText.text = isWin
            ? $"You Won ₹{amount}"
            : $"You Lose ₹{Mathf.Abs(amount)}";

        winloseText.color = isWin ? Color.green : Color.red;
        reactionEmoji.sprite = GetReactionEmoji(isWin);
        //reactionEmoji.gameObject.SetActive(true);
    }

    public void UpdateLastRoundResults(int[] results)
    {
        for (int i = 0; i < lastRoundResults.Length; i++)
            lastRoundResults[i].text = i < results.Length ? results[i].ToString() : "-";
    }

    #endregion

    #region Helpers

    private Sprite GetReactionEmoji(bool isWin)
    {
        var list = isWin ? winEmojiesReaction : loseEmojiesReaction;
        return list[UnityEngine.Random.Range(0, list.Count)];
    }

    private void ShowInsufficientBalance()
    {
        if (insufficientBalance.gameObject.activeSelf) return;

        insufficientBalance.gameObject.SetActive(true);
        insufficientBalance.rectTransform
            .DOScale(Vector3.one, 0.3f)
            .From(Vector3.zero)
            .SetEase(Ease.OutBack);

        DOVirtual.DelayedCall(2f, () =>
        {
            insufficientBalance.gameObject.SetActive(false);
        });
    }

    private void AnimateCoin(Vector3 startPos, int diceNumber, float amount)
    {
        Transform target = diceNumbers[diceNumber - 1].transform;

        GameObject coin = Instantiate(animateCoin, transform);
        coin.SetActive(true);

        coin.transform.GetChild(0)
            .GetComponent<TextMeshProUGUI>().text = amount.ToString();

        RectTransform rt = coin.GetComponent<RectTransform>();
        rt.position = startPos;
        rt.localScale = Vector3.one;

        Sequence seq = DOTween.Sequence();

        seq.Append(
           rt.DOMove(target.position, 0.2f)
             .SetEase(Ease.InQuad)
        );

        //seq.Join(
        //    rt.DOScale(0.85f, 0.4f)
        //);

        seq.OnComplete(() =>
        {
            coin.transform.SetParent(target, worldPositionStays: false);
            rt.anchoredPosition = Vector2.zero;
            rt.DOScale(0.65f, 0.07f);

            betStack.Push(new BetCoin
            {
                coinObj = coin,
                diceNumber = diceNumber,
                amount = amount
            });
        });
    }

    public void RemoveLastBet()
    {
        if (betStack.Count == 0) return;

        BetCoin lastBet = betStack.Pop();

        // Optional: animate back to main chip
        //RectTransform rt = lastBet.coinObj.GetComponent<RectTransform>();
        //rt.SetParent(transform);

        //rt.DOMove(mainChipPos.position, 0.3f)
        //    .SetEase(Ease.InBack)
        //    .OnComplete(() =>
        //    {
        //        Destroy(lastBet.coinObj);
        //    });

        UpdateBalance(GameManager.Instance.WalletAmount);
    }

    public void RemoveAllBets()
    {
        while (betStack.Count > 0)
        {
            BetCoin bet = betStack.Pop();
            Destroy(bet.coinObj);
        }
    }

    #endregion
}

[System.Serializable]
public class BetCoin
{
    public GameObject coinObj;
    public int diceNumber;
    public float amount;
}