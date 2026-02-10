using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

public enum RoundStatus
{
    NONE,
    WAITING,
    BETTING,
    CLOSED,
    RESULT,
    COMPLETED
}

public class GameController : MonoBehaviour
{
    [Header("References")]
    public DiceCameraController diceCamController;

    private GameApiClient apiClient;
    private GameplayUIManager gameplayui;
    private DiceAndBox diceBox;

    private RoundStatus currentStatus;
    private GameApiClient.RoundData currentRoundData;

    // Cache last dice result (late join support)
    private int[] lastDiceValues;

    private List<GameApiClient.MyBet> currentRoundBets;
    private int timer = 0;
    private static bool isFreshLaunched = true;

    private void Start()
    {
        apiClient = GameManager.Instance.ApiClient;

        gameplayui = UIManager.Instance.gameplayUIManager;
        diceBox = FindFirstObjectByType<DiceAndBox>();

        SubscribeEvents();
    }

    private void OnDestroy()
    {
        UnsubscribeEvents();
    }

    private void OnApplicationFocus(bool focus)
    {
        if (focus)
        {
            if (!isFreshLaunched)
                OnPlayerJoinOrResume(timer);
            else
                isFreshLaunched = false;
        }
    }

    #region WebSocket Events

    private void SubscribeEvents()
    {
        apiClient.OnGameState += HandleGameState;
        apiClient.OnTimerUpdate += HandleTimerUpdate;
        apiClient.OnGameStart += HandleGameStart;
        apiClient.OnDiceRollWarn += HandleDiceRollWarn;
        apiClient.OnDiceResult += HandleDiceResult;
        apiClient.OnResultAnn += HandleResultAnn;
        apiClient.OnGameEnd += HandleGameEnd;
        apiClient.OnRoundUpdate += HandleRoundUpdate;
        apiClient.OnShowHidePopup += UIManager.Instance.ShowNoInternetPopup;
        apiClient.OnLoginSuccess += FetchCurrentRound;
    }

    private void UnsubscribeEvents()
    {
        apiClient.OnGameState -= HandleGameState;
        apiClient.OnTimerUpdate -= HandleTimerUpdate;
        apiClient.OnGameStart -= HandleGameStart;
        apiClient.OnDiceRollWarn -= HandleDiceRollWarn;
        apiClient.OnDiceResult -= HandleDiceResult;
        apiClient.OnResultAnn -= HandleResultAnn;
        apiClient.OnGameEnd -= HandleGameEnd;
        apiClient.OnRoundUpdate -= HandleRoundUpdate;
        apiClient.OnShowHidePopup -= UIManager.Instance.ShowNoInternetPopup;
    }

    #endregion

    #region UI Updates

    public void UpdateResult()
    {
        GameManager.Instance.ApiClient.GetWinningResults((ok, result, err) =>
        {
            if (ok && result != null)
            {
                List<Tuple<int, int>> winnings = new List<Tuple<int, int>>();
                foreach (var win in result.WinningNumbers)
                {
                    winnings.Add(new Tuple<int, int>(win.Number, win.Frequency));
                }
                gameplayui.UpdateRollDiceNum(winnings);
            }
        });
    }

    #endregion

    #region Initial Fetch

    private void FetchCurrentRound()
    {
        apiClient.GetCurrentRound((ok, data, err) =>
        {
            if (!ok || data == null) return;

            currentRoundData = data;
            UpdateRoundStatusFromString(data.Status);
        });
    }

    #endregion

    #region Bet Management

    public void PlaceBet(int diceNo, float amount, Action<bool> onResult)
    {
        float walletAmount = GameManager.Instance.WalletAmount;

        if (amount > walletAmount)
        {
            onResult?.Invoke(false);
            return;
        }

        apiClient.PlaceBet(diceNo, amount, (ok, betResp, err) =>
        {
            if (!ok)
            {
                onResult?.Invoke(false);
                return;
            }

            GameManager.Instance.RefreshWallet();
            onResult?.Invoke(true);
        });
    }

    public void RemoveLastBets()
    {
        if (currentRoundBets.Count <= 0) return;

        apiClient.DeleteBet(currentRoundBets[0].number, (ok, err) =>
        {
            if (ok)
                GameManager.Instance.RefreshWallet();
        });
    }

    public void GetCurrentRoundBets(Action onComplete)
    {
        GameManager.Instance.GetMyBets((bets) =>
        {
            if (bets == null) return;
            currentRoundBets = bets
                .Where(b => b.round_id == currentRoundData.RoundId)
                .ToList();
            onComplete?.Invoke();
        });
    }

    #endregion

    #region GAME FLOW

    private void HandleGameState(GameApiClient.GameState gs)
    {
        if (gs == null) return;

        UpdateRoundStatusFromString(gs.status);

        int timer = gs.timer;
        OnPlayerJoinOrResume(timer);
    }

    private void HandleTimerUpdate(GameApiClient.TimerUpdate tu)
    {
        if (tu == null) return;

        timer = tu.timer;
        UpdateRoundStatusFromString(tu.status);
        gameplayui.UpdateTimer(timer);
    }

    private void HandleGameStart(GameApiClient.GameStart gs)
    {
        apiClient.GetLastRoundResult((ok, r, e) =>
        {
            if (!ok || r == null) return;
            CacheLastResult(r);
            gameplayui.UpdateLastRoundResults(lastDiceValues);
        });
    }

    private void HandleDiceRollWarn(GameApiClient.DiceRollWarning warn)
    {
        diceCamController.MoveCamera(DiceCameraState.DiceView, true);
        diceBox.ShakeDiceIfNeeded();
    }

    private void HandleDiceResult(GameApiClient.DiceResult dr)
    {
        if (dr?.dice_values == null) return;

        lastDiceValues = dr.dice_values;

        diceBox.ThrowDiceIfNeeded(lastDiceValues);

        FetchCurrentRound();
        UpdateResult();
        GameManager.Instance.ApiClient.GetRoundResult(dr.round_id, (ok, result, err) =>
        {
            if (ok && result != null)
            {
                gameplayui.UpdateWinLoseText(float.Parse(result.Summary.NetResult));
            }
        });
    }

    private void HandleResultAnn(GameApiClient.ResultAnnouncement res)
    {
        UpdateResult();
        GameManager.Instance.RefreshWallet();
        GameManager.Instance.ApiClient.GetRoundResult(currentRoundData.RoundId, (ok, result, err) =>
        {
            if (ok && result != null)
            {
                gameplayui.UpdateWinLoseText(float.Parse(result.Summary.NetResult));
            }
        });
    }

    private void HandleGameEnd(GameApiClient.GameEnd ge)
    {
        diceCamController.MoveCamera(DiceCameraState.BettingView, true);
        diceBox.ResetDice();

        lastDiceValues = null;

        GameManager.Instance.RefreshWallet();
        gameplayui.RemoveAllBets();
    }

    private void HandleRoundUpdate(GameApiClient.RoundUpdate ru)
    {
        diceBox.ResetDice();
    }

    #endregion

    #region Helpers

    private void CacheLastResult(GameApiClient.LastRoundResult r)
    {
        lastDiceValues = new[]
        {
            r.dice1_value, r.dice2_value, r.dice3_value,
            r.dice4_value, r.dice5_value, r.dice6_value
        };
    }

    private void UpdateRoundStatusFromString(string status)
    {
        if (!Enum.TryParse(status, true, out RoundStatus rs)) return;
        if (currentStatus == rs) return;

        currentStatus = rs;
        gameplayui.UpdateGameUI(currentStatus, GameManager.Instance.WalletAmount);
    }

    private void OnPlayerJoinOrResume(int currentTime)
    {
        if (GameManager.Instance.GameSettings == null) return;
        int diceRollTime = GameManager.Instance.GameSettings.DiceRollTime;
        int diceResultTime = GameManager.Instance.GameSettings.DiceResultTime;
        int roundEndTime = GameManager.Instance.GameSettings.RoundEndTime;

        bool inDiceRollPhase = currentTime >= diceRollTime && currentTime < diceResultTime;
        bool afterDiceResult = currentTime >= diceResultTime;

        // Camera
        diceCamController.MoveCamera(
            inDiceRollPhase || afterDiceResult
                ? DiceCameraState.DiceView
                : DiceCameraState.BettingView,
            false
        );

        // Dice reconstruction
        if (inDiceRollPhase)
        {
            diceBox.ShakeDiceIfNeeded();
        }

        apiClient.GetLastRoundResult((ok, r, e) =>
        {
            if (!ok || r == null) return;
            CacheLastResult(r);
            gameplayui.SetGameUI(currentStatus, GameManager.Instance.WalletAmount, lastDiceValues);
            if (afterDiceResult && currentTime < roundEndTime && !diceBox.diceRoller.IsDiceAlreadySpawned())
            {
                diceBox.diceRoller.SpawnDices(lastDiceValues);
            }
        });
    }

    #endregion
}