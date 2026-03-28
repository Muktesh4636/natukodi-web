using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using static GameApiClient;

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

    // reconnect coroutine & config
    private Coroutine reconnectRoutine;
    private int reconnectAttempt = 0;
    private const int MAX_RECONNECT_ATTEMPTS = -1; // -1 = infinite
    private const float RECONNECT_BASE_DELAY = 1.0f;
    private const float RECONNECT_MAX_DELAY = 15f;

    private void Start()
    {
        apiClient = GameManager.Instance.ApiClient;

        gameplayui = UIManager.Instance.gameplayUIManager;
        diceBox = FindFirstObjectByType<DiceAndBox>();

        // subscribe to dice playback complete so SFX plays only when dice land
        if (diceBox != null && diceBox.diceRoller != null)
            diceBox.diceRoller.OnPlaybackComplete += HandleDicePlaybackComplete;

        SubscribeEvents();
    }

    private void OnDestroy()
    {
        // unsubscribe playback event
        if (diceBox != null && diceBox.diceRoller != null)
            diceBox.diceRoller.OnPlaybackComplete -= HandleDicePlaybackComplete;

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

            // When returning to app, if websocket unhealthy, attempt reconnect
            TryResumeReconnect();
        }
    }

    private void OnApplicationPause(bool paused)
    {
        if (!paused)
        {
            // resumed
            TryResumeReconnect();
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

        // reconnect UI hooks
        apiClient.OnDisconnected += HandleApiDisconnected;
        apiClient.OnConnected += HandleApiConnected;
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
        apiClient.OnLoginSuccess -= FetchCurrentRound;

        apiClient.OnDisconnected -= HandleApiDisconnected;
        apiClient.OnConnected -= HandleApiConnected;
    }

    #endregion

    #region UI Updates

    public void UpdateResult()
    {
        if (apiClient == null || gameplayui == null)
        {
            Debug.LogWarning("UpdateResult aborted: apiClient or gameplayui is null.");
            return;
        }

        void CallAllApis()
        {
            // 1️⃣ Winning Frequency (Independent)
            apiClient.GetWinningFrequency((okFreq, winResp, errFreq) =>
            {
                if (okFreq && winResp != null && winResp.WinningNumbers != null)
                {
                    try
                    {
                        var winnings = new List<Tuple<int, int>>();
                        var numbersWithLightning = new HashSet<int>();
                        foreach (var win in winResp.WinningNumbers)
                        {
                            winnings.Add(new Tuple<int, int>(win.Number, win.Frequency));
                            if (win.Frequency > 2)
                                numbersWithLightning.Add(win.Number);
                        }

                        gameplayui.UpdateFrequencyOfNum(winnings);
                        if (diceBox != null && numbersWithLightning.Count > 0)
                            diceBox.ApplyLightningForNumbers(numbersWithLightning);
                    }
                    catch (Exception ex)
                    {
                        Debug.LogWarning("WinningFrequency error: " + ex);
                    }
                }
                else
                {
                    Debug.LogWarning("GetWinningFrequency failed: " + errFreq);
                }
            });

            // 2️⃣ Round Result (Independent)
            if (!string.IsNullOrEmpty(currentRoundData?.RoundId))
            {
                apiClient.GetCurrentRoundResult((okRound, roundResp, errRound) =>
                {
                    if (okRound && roundResp != null)
                    {
                        Debug.Log("Net Result : " + roundResp.Summary.NetResult);
                        gameplayui.UpdateWinLoseText(roundResp.Summary.NetResult);
                    }
                    else
                    {
                        Debug.LogWarning("GetRoundResult failed: " + errRound);
                    }
                });
            }

            // 3️⃣ Last Round Result (Independent)
            apiClient.GetLastRoundResult((okLast, last, errLast) =>
            {
                if (!okLast || last == null)
                {
                    Debug.LogWarning("GetLastRoundResult failed: " + errLast);
                    return;
                }

                CacheLastResult(last);

                bool afterDiceResult =
                    timer > (GameManager.Instance.GameSettings?.DiceResultTime ?? 0);

                gameplayui.UpdateRoundResults(lastDiceValues, afterDiceResult);
            });
        }

        // 🔹 First update CurrentRoundData
        if (currentRoundData == null || string.IsNullOrEmpty(currentRoundData.RoundId))
        {
            apiClient.GetCurrentRound((okCurrent, data, errCurrent) =>
            {
                if (okCurrent && data != null)
                {
                    currentRoundData = data;
                    try
                    {
                        UpdateRoundStatusFromString(data.Status);
                    }
                    catch { }
                }

                // After updating current round → call all APIs
                CallAllApis();
            });
        }
        else
        {
            // Already have current round → directly call APIs
            CallAllApis();
        }
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

    #endregion

    #region GAME FLOW

    private void HandleGameState(GameApiClient.GameState gs)
    {
        if (gs == null) return;

        // Do not fetch current round on every state event — only update status and recover UI based on timer.
        UpdateRoundStatusFromString(gs.status);

        int timer = gs.timer;
        OnPlayerJoinOrResume(timer);
    }

    private void HandleTimerUpdate(GameApiClient.TimerUpdate tu)
    {
        if (tu == null) return;

        // Avoid fetching round data on every timer tick; update timer and status only when necessary.
        timer = tu.timer;
        UpdateRoundStatusFromString(tu.status);
        gameplayui.UpdateTimer(timer);
    }

    private void HandleGameStart(GameApiClient.GameStart gs)
    {
        // Play place-bet sound to indicate a new round started
        SafePlaySfx(SfxType.PlaceBetSfx, loop: false);

        // When a new round starts ensure box is on table and camera is in betting view.
        try
        {
            if (diceBox != null)
                diceBox.SetBoxToTableImmediate();
        }
        catch { }

        try
        {
            if (diceCamController != null)
                diceCamController.MoveCamera(DiceCameraState.BettingView, false);
        }
        catch { }

        apiClient.GetLastRoundResult((ok, r, e) =>
        {
            if (!ok || r == null) return;
            CacheLastResult(r);
            gameplayui.UpdateRoundResults(lastDiceValues, false);
        });
    }

    private void HandleDiceRollWarn(GameApiClient.DiceRollWarning warn)
    {
        // Transition to dice camera and shake the box
        if (diceCamController != null)
            diceCamController.MoveCamera(DiceCameraState.DiceView, true);

        if (diceBox != null)
            diceBox.ShakeDiceIfNeeded();

        // Start looping shaking SFX while box is shaking
        SafePlaySfx(SfxType.ShakingSfx, loop: true);

        // Pause background music while shaking
        try { AudioManager.Instance?.PauseBackgroundMusic(); } catch { }
    }

    private void HandleDiceResult(GameApiClient.DiceResult dr)
    {
        if (dr?.dice_values == null) return;

        lastDiceValues = dr.dice_values;

        // Ensure camera is on dice view, then throw (physics) the dice.
        if (diceCamController != null)
            diceCamController.MoveCamera(DiceCameraState.DiceView, true);

        if (diceBox != null)
            diceBox.ThrowDiceIfNeeded(lastDiceValues);

        // Stop shaking SFX immediately when throw begins (loop should stop)
        SafeStopLoopingSfx();

        // Pause background music while dice are in flight / rolling
        try { AudioManager.Instance?.PauseBackgroundMusic(); } catch { }

        // DO NOT play DiceRollSfx here — wait for actual playback completion (handled in HandleDicePlaybackComplete)
    }

    // Called when physics playback finished and dice are settled on table
    private void HandleDicePlaybackComplete(int[] results)
    {
        try
        {
            // Resume background music now that dice have landed
            try { AudioManager.Instance?.PlayBackgroundMusic(); } catch { }
        }
        catch (Exception ex)
        {
            Debug.LogWarning("HandleDicePlaybackComplete error: " + ex.Message);
        }
    }

    private void HandleResultAnn(GameApiClient.ResultAnnouncement res)
    {
        GameManager.Instance.RefreshWallet();

        // use currentRoundData if available; otherwise GetRoundResult for the announced round.
        string roundId = currentRoundData?.RoundId ?? res?.round_id;
        if (string.IsNullOrEmpty(roundId)) return;

        apiClient.GetCurrentRoundResult((ok, result, err) =>
        {
            if (ok && result != null)
            {
                gameplayui.UpdateWinLoseText(result.Summary.NetResult);
            }
        });
    }

    private void HandleGameEnd(GameApiClient.GameEnd ge)
    {
        // Camera back to betting and remove any dice visuals
        if (diceCamController != null)
            diceCamController.MoveCamera(DiceCameraState.BettingView, true);

        if (diceBox != null)
            diceBox.ResetDice();

        lastDiceValues = null;

        // Ensure any looping sfx stopped
        SafeStopLoopingSfx();

        // Make sure background music is resumed when round ends
        try { AudioManager.Instance?.PlayBackgroundMusic(); } catch { }

        GameManager.Instance.RefreshWallet();
        gameplayui.RemoveAllBets();
        gameplayui.ShowHideWinLoseText();
        gameplayui.HideFrequencyOfNumber();
    }

    private void HandleRoundUpdate(GameApiClient.RoundUpdate ru)
    {
        if (diceBox != null)
            diceBox.ResetDice();
    }

    #endregion

    #region Reconnect Handling

    private void HandleApiDisconnected()
    {
        // Show reconnect UI and start reconnect attempts
        try
        {
            gameplayui?.ShowReconnectPanel(true);
            StartReconnectRoutine();
        }
        catch { }
    }

    private void HandleApiConnected()
    {
        // Hide reconnect UI and stop reconnect attempts
        try
        {
            StopReconnectRoutine();
            gameplayui?.ShowReconnectPanel(false);
        }
        catch { }
    }

    private void StartReconnectRoutine()
    {
        if (reconnectRoutine != null) return;
        reconnectAttempt = 0;
        reconnectRoutine = StartCoroutine(ReconnectCoroutine());
    }

    private void StopReconnectRoutine()
    {
        if (reconnectRoutine != null)
        {
            try { StopCoroutine(reconnectRoutine); } catch { }
            reconnectRoutine = null;
        }
    }

    private IEnumerator ReconnectCoroutine()
    {
        while (true)
        {
            // If websocket already healthy, stop
            if (apiClient.IsWebSocketHealthy())
            {
                HandleApiConnected();
                yield break;
            }

            // attempt reconnect
            reconnectAttempt++;
            try
            {
                apiClient.ReconnectWebSocket();
            }
            catch (Exception ex)
            {
                Debug.LogWarning("Reconnect attempt failed: " + ex.Message);
            }

            // exponential backoff
            float delay = Mathf.Min(RECONNECT_BASE_DELAY * Mathf.Pow(2, reconnectAttempt - 1), RECONNECT_MAX_DELAY);
            yield return new WaitForSeconds(delay);

            // continue attempts unless max attempt reached
            if (MAX_RECONNECT_ATTEMPTS > 0 && reconnectAttempt >= MAX_RECONNECT_ATTEMPTS)
                break;
        }

        reconnectRoutine = null;
    }

    private void TryResumeReconnect()
    {
        // if websocket is unhealthy, show reconnect UI and start attempts
        if (apiClient == null) return;

        if (!apiClient.IsWebSocketHealthy())
        {
            gameplayui?.ShowReconnectPanel(true);
            StartReconnectRoutine();
        }
    }

    #endregion

    #region Audio Helpers

    private void SafePlaySfx(SfxType sfx, bool loop = false)
    {
        try
        {
            if (AudioManager.Instance != null)
                AudioManager.Instance.PlaySfx(sfx, loop);
        }
        catch { }
    }

    // Stop only looping SFX (we call StopSfx which stops all; acceptable here)
    private void SafeStopLoopingSfx()
    {
        try
        {
            if (AudioManager.Instance != null)
                AudioManager.Instance.StopSfx();
        }
        catch { }
    }

    #endregion

    #region Helpers

    private void CacheLastResult(GameApiClient.LastRoundResult r)
    {
        lastDiceValues = new[] { r.dice1, r.dice2, r.dice3, r.dice4, r.dice5, r.dice6 };
    }

    private void UpdateRoundStatusFromString(string status)
    {
        if (!Enum.TryParse(status, true, out RoundStatus rs)) return;
        if (currentStatus == rs) return;

        // If status changed to CLOSED -> play close bet sfx
        if (rs == RoundStatus.CLOSED)
        {
            SafePlaySfx(SfxType.CloseBetSfx, loop: false);
        }

        currentStatus = rs;
        apiClient.GetBetAmountSummary((success, summary, err) =>
        {
            BetAmountSummary[] summaryToSend;

            if (success && summary != null && summary.Count > 0)
            {
                summaryToSend = summary.ToArray();
            }
            else
            {
                // Create default summary (1 to 6 with amount 0)
                summaryToSend = new BetAmountSummary[6];

                for (int i = 0; i < 6; i++)
                {
                    summaryToSend[i] = new BetAmountSummary
                    {
                        number = i + 1,
                        amount = 0
                    };
                }
            }

            gameplayui.UpdateGameUI(
                currentStatus,
                GameManager.Instance.WalletAmount,
                summaryToSend
            );
        });
    }

    private void OnPlayerJoinOrResume(int currentTime)
    {
        if (GameManager.Instance.GameSettings == null) return;
        // Avoid fetching current round repeatedly here; only refresh status.
        FetchCurrentRound();

        int diceRollTime = GameManager.Instance.GameSettings.DiceRollTime;
        int diceResultTime = GameManager.Instance.GameSettings.DiceResultTime;
        int roundEndTime = GameManager.Instance.GameSettings.RoundEndTime;

        bool inDiceRollPhase = currentTime >= diceRollTime && currentTime < diceResultTime;
        bool afterDiceResult = currentTime >= diceResultTime;

        // Camera: dice view for roll/result phases, betting otherwise.
        if (diceCamController != null)
            diceCamController.MoveCamera(
                inDiceRollPhase || afterDiceResult
                    ? DiceCameraState.DiceView
                    : DiceCameraState.BettingView,
                false
            );

        // Dice reconstruction
        if (inDiceRollPhase)
        {
            if (diceBox != null)
                diceBox.ShakeDiceIfNeeded();

            // start shaking sfx for late joiner if currently in roll phase
            SafePlaySfx(SfxType.ShakingSfx, loop: true);
            try { AudioManager.Instance?.PauseBackgroundMusic(); } catch { }
        }
        else
        {
            // not in roll phase -> ensure shaking sfx stopped
            SafeStopLoopingSfx();
        }

        if (currentStatus == RoundStatus.CLOSED)
            AudioManager.Instance?.PlaySfx(SfxType.CloseBetSfx, loop: false);
        else if (currentStatus == RoundStatus.BETTING)
            AudioManager.Instance?.PlaySfx(SfxType.PlaceBetSfx, loop: false);

        // Only spawn static (non-physics) dice when a player joins after the dice-result time.
        apiClient.GetLastRoundResult((ok, r, e) =>
        {
            if (!ok || r == null) return;
            CacheLastResult(r);
            apiClient.GetBetAmountSummary((success, Summary, err) =>
            {
                BetAmountSummary[] summaryToSend;

                if (success && Summary != null && Summary.Count > 0)
                {
                    summaryToSend = Summary.ToArray();
                }
                else
                {
                    // Create default summary (1 to 6 with amount 0)
                    summaryToSend = new BetAmountSummary[6];

                    for (int i = 0; i < 6; i++)
                    {
                        summaryToSend[i] = new BetAmountSummary
                        {
                            number = i + 1,
                            amount = 0
                        };
                    }
                }

                apiClient.GetMaxBetAmountSummary((done, maxBetResponse, err) =>
                {
                    if (done && maxBetResponse != null && maxBetResponse != null)
                    {
                        gameplayui.SetGameUI(currentStatus, GameManager.Instance.WalletAmount, lastDiceValues,
                                         afterDiceResult, summaryToSend, maxBetResponse.max_bet_amount);
                    }
                    else
                    {
                        gameplayui.SetGameUI(currentStatus, GameManager.Instance.WalletAmount, lastDiceValues,
                                         afterDiceResult, summaryToSend, -1);
                    }
                });
            });

            if (afterDiceResult && currentTime < roundEndTime && !diceBox.diceRoller.IsDiceAlreadySpawned())
            {
                // spawn static representation so late-joiner sees final dice without physics simulation
                diceBox.SpawnDices(lastDiceValues);
            }
        });
    }

    #endregion
}