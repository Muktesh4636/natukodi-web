using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NativeWebSocket;
using UnityEngine;
using UnityEngine.Networking;

/// <summary>
/// GameApiClient - Manages REST API calls and a NativeWebSocket connection for realtime game events.
/// Designed to be attached to a Unity GameObject.
/// </summary>
public class GameApiClient : MonoBehaviour
{
    [Header("API Config")]
    [Tooltip("Base HTTP URL (no trailing slash)")]
    [SerializeField] private string baseUrl = "http://159.198.46.36:8232";

    [Tooltip("Base WebSocket URL (ws://host:port/ws/game/)")]
    [SerializeField] private string wsUrl = "ws://159.198.46.36:8232/ws/game/";

    // Auth tokens (kept in memory; persist externally if desired)
    private string accessToken = null;
    private string refreshToken = null;

    // WebSocket
    private WebSocket websocket;
    private bool wsConnected = false;

    // Main-thread queue for background callbacks
    private readonly ConcurrentQueue<Action> mainThreadQueue = new ConcurrentQueue<Action>();

    [Header("Connection Monitoring")]
    [SerializeField] private float connectionCheckInterval = 3f;

    private bool isPlayerLoggedIn = false;
    private bool popupVisible = false;
    private Coroutine connectionMonitorRoutine;

    // Events
    public event Action OnConnected;
    public event Action OnDisconnected;
    public event Action OnReconnect;
    public event Action OnLoginSuccess;
    public event Action<string> OnError;

    // Server -> client events
    public event Action<GameState> OnGameState;
    public event Action<TimerUpdate> OnTimerUpdate;
    public event Action<GameStart> OnGameStart;
    public event Action<DiceRollWarning> OnDiceRollWarn;
    public event Action<DiceResult> OnDiceResult;
    public event Action<ResultAnnouncement> OnResultAnn;
    public event Action<GameEnd> OnGameEnd;
    public event Action<RoundUpdate> OnRoundUpdate;

    // popup events
    public event Action<bool> OnShowHidePopup;

    private const string JSON_CONTENT = "application/json";

    // WebSocket delegate fields (declare once) — use NativeWebSocket delegate types
    private WebSocketOpenEventHandler wsOnOpen;
    private WebSocketCloseEventHandler wsOnClose;
    private WebSocketErrorEventHandler wsOnError;
    private WebSocketMessageEventHandler wsOnMessage;

    // Simple short-lived caches to reduce duplicate network calls
    private RoundData cachedRoundData;
    private float cachedRoundTimestamp = 0f;
    private GameSettings cachedGameSettings;
    private float cachedSettingsTimestamp = 0f;
    private const float ROUND_CACHE_TTL = 1f;      // 1 second cache for current round
    private const float SETTINGS_CACHE_TTL = 5f;   // 5 seconds cache for settings

    #region Models

    [Serializable]
    public class AuthResponse { public string access; public string refresh; }

    [Serializable]
    public class WalletResponse { public string balance; }

    [Serializable]
    public class RegisterationErrorResponse
    {
        [JsonProperty("username")]
        public List<string> UsernameErrors { get; set; }
        [JsonProperty("password")]
        public List<string> PasswordErrors { get; set; }
    }

    [Serializable]
    public class GameSettings
    {
        [JsonProperty("BETTING_DURATION")]
        public int BettingDuration { get; set; }

        [JsonProperty("RESULT_SELECTION_DURATION")]
        public int ResultSelectionDuration { get; set; }

        [JsonProperty("RESULT_DISPLAY_DURATION")]
        public int ResultDisplayDuration { get; set; }

        [JsonProperty("TOTAL_ROUND_DURATION")]
        public int TotalRoundDuration { get; set; }

        [JsonProperty("DICE_ROLL_TIME")]
        public int DiceRollTime { get; set; }

        [JsonProperty("BETTING_CLOSE_TIME")]
        public int BettingCloseTime { get; set; }

        [JsonProperty("DICE_RESULT_TIME")]
        public int DiceResultTime { get; set; }

        [JsonProperty("RESULT_ANNOUNCE_TIME")]
        public int ResultAnnounceTime { get; set; }

        [JsonProperty("ROUND_END_TIME")]
        public int RoundEndTime { get; set; }

        [JsonProperty("CHIP_VALUES")]
        public List<int> ChipValues { get; set; }

        [JsonProperty("PAYOUT_RATIOS")]
        public Dictionary<string, float> PayoutRatios { get; set; }
    }

    [Serializable]
    public class BetAmountSummary
    {
        [JsonProperty("number")]
        public int number { get; set; }
        [JsonProperty("amount")]
        public int amount { get; set; }
    }

    [Serializable]
    public class MaxBetResponse
    {
        [JsonProperty("max_bet")]
        public int max_bet_amount { get; set; }
    }

    public class PaymentMethod
    {
        [JsonProperty("id")]
        public int id { get; set; }

        [JsonProperty("name")]
        public string name { get; set; }

        [JsonProperty("method_type")]
        public PaymentMethodType method_type { get; set; }

        [JsonProperty("account_name")]
        public string account_name { get; set; }

        [JsonProperty("bank_name")]
        public string bank_name { get; set; }

        [JsonProperty("upi_id")]
        public string upi_id { get; set; }

        [JsonProperty("link")]
        public string link { get; set; }

        [JsonProperty("account_number")]
        public string account_number { get; set; }

        [JsonProperty("ifsc_code")]
        public string ifsc_code { get; set; }

        [JsonProperty("is_active")]
        public bool is_active { get; set; }

        [JsonProperty("created_at")]
        public string created_at { get; set; }

        [JsonProperty("updated_at")]
        public string updated_at { get; set; }
    }

    [Serializable]
    public class RemoveLastBetResponse
    {
        [JsonProperty("message")]
        public string message;

        [JsonProperty("refund_amount")]
        public string refund_amount;

        [JsonProperty("bet_number")]
        public int bet_number;

        [JsonProperty("wallet_balance")]
        public string wallet_balance;

        [JsonProperty("round")]
        public RemoveLastBetRound round;
    }

    [Serializable]
    public class RemoveLastBetRound
    {
        [JsonProperty("round_id")]
        public string round_id;

        [JsonProperty("total_bets")]
        public int total_bets;

        [JsonProperty("total_amount")]
        public string total_amount;
    }

    [Serializable]
    public class DepositProofResponse
    {
        [JsonProperty("id")]
        public int id { get; set; }

        [JsonProperty("user")]
        public User user { get; set; }

        [JsonProperty("amount")]
        public string amount { get; set; }

        [JsonProperty("status")]
        public string status { get; set; }

        [JsonProperty("screenshot_url")]
        public string screenshot_url { get; set; }

        [JsonProperty("admin_note")]
        public string admin_note { get; set; }

        [JsonProperty("created_at")]
        public string created_at { get; set; }

        [JsonProperty("updated_at")]
        public string updated_at { get; set; }
    }

    [Serializable]
    public class User
    {
        [JsonProperty("id")]
        public int id { get; set; }

        [JsonProperty("username")]
        public string username { get; set; }

        [JsonProperty("email")]
        public string email { get; set; }

        [JsonProperty("phone_number")]
        public string phone_number { get; set; }

        [JsonProperty("date_joined")]
        public string date_joined { get; set; }

        [JsonProperty("is_staff")]
        public bool is_staff { get; set; }
    }


    [Serializable]
    public class RoundResultResponse
    {
        [JsonProperty("round")]
        public RoundInfo Round { get; set; }

        [JsonProperty("bets")]
        public List<BetInfo> Bets { get; set; }

        [JsonProperty("summary")]
        public RoundSummary Summary { get; set; }

        [JsonProperty("wallet_balance")]
        public string WalletBalance { get; set; } // keep string for money
    }

    [Serializable]
    public class RoundInfo
    {
        [JsonProperty("round_id")]
        public string RoundId { get; set; }

        [JsonProperty("status")]
        public string Status { get; set; }

        [JsonProperty("dice_result")]
        public string DiceResult { get; set; }

        [JsonProperty("dice_1")]
        public int Dice1 { get; set; }

        [JsonProperty("dice_2")]
        public int Dice2 { get; set; }

        [JsonProperty("dice_3")]
        public int Dice3 { get; set; }

        [JsonProperty("dice_4")]
        public int Dice4 { get; set; }

        [JsonProperty("dice_5")]
        public int Dice5 { get; set; }

        [JsonProperty("dice_6")]
        public int Dice6 { get; set; }

        [JsonProperty("start_time")]
        public DateTime StartTime { get; set; }

        [JsonProperty("result_time")]
        public DateTime ResultTime { get; set; }
    }

    [Serializable]
    public class BetInfo
    {
        [JsonProperty("id")]
        public int Id { get; set; }

        [JsonProperty("number")]
        public int Number { get; set; }

        [JsonProperty("chip_amount")]
        public string ChipAmount { get; set; }

        [JsonProperty("is_winner")]
        public bool IsWinner { get; set; }

        [JsonProperty("payout_amount")]
        public string PayoutAmount { get; set; }
    }

    [Serializable]
    public class RoundSummary
    {
        [JsonProperty("total_bets")]
        public int TotalBets { get; set; }

        [JsonProperty("total_bet_amount")]
        public string TotalBetAmount { get; set; }

        [JsonProperty("total_payout")]
        public string TotalPayout { get; set; }

        [JsonProperty("net_result")]
        public int NetResult { get; set; }

        [JsonProperty("winning_bets")]
        public int WinningBets { get; set; }

        [JsonProperty("losing_bets")]
        public int LosingBets { get; set; }
    }

    [Serializable]
    public class GameState
    {
        [JsonProperty("type")] public string type { get; set; }
        [JsonProperty("round_id")] public string round_id { get; set; }
        [JsonProperty("status")] public string status { get; set; }
        [JsonProperty("timer")] public int timer { get; set; }
    }

    [Serializable]
    public class TimerUpdate
    {
        [JsonProperty("type")] public string type { get; set; }
        [JsonProperty("timer")] public int timer { get; set; }
        [JsonProperty("status")] public string status { get; set; }
        [JsonProperty("round_id")] public string round_id { get; set; }
    }

    [Serializable]
    public class GameStart
    {
        [JsonProperty("type")] public string type { get; set; }
        [JsonProperty("round_id")] public string round_id { get; set; }
        [JsonProperty("status")] public string status { get; set; }
        [JsonProperty("timer")] public int timer { get; set; }
    }

    [Serializable]
    public class DiceRollWarning
    {
        [JsonProperty("type")] public string type { get; set; }
        [JsonProperty("round_id")] public string round_id { get; set; }
        [JsonProperty("status")] public string status { get; set; }
        [JsonProperty("timer")] public int timer { get; set; }

        [JsonProperty("dice_roll_time")]
        public int dice_roll_time { get; set; }
    }

    [Serializable]
    public class DiceResult
    {
        [JsonProperty("type")]
        public string type { get; set; }

        [JsonProperty("round_id")]
        public string round_id { get; set; }

        [JsonProperty("status")]
        public string status { get; set; }

        [JsonProperty("timer")]
        public int timer { get; set; }

        [JsonProperty("result")]
        public string result { get; set; }

        [JsonProperty("dice_values")]
        public int[] dice_values { get; set; }
    }

    [Serializable]
    public class LastRoundResult
    {
        [JsonProperty("round_id")]
        public string roundId;

        [JsonProperty("dice_1")]
        public int dice1;

        [JsonProperty("dice_2")]
        public int dice2;

        [JsonProperty("dice_3")]
        public int dice3;

        [JsonProperty("dice_4")]
        public int dice4;

        [JsonProperty("dice_5")]
        public int dice5;

        [JsonProperty("dice_6")]
        public int dice6;

        [JsonProperty("dice_result")]
        public string diceResult;  

        [JsonProperty("timestamp")]
        public string timestamp;   
    }

    [Serializable]
    public class ResultAnnouncement
    {
        [JsonProperty("type")] public string type { get; set; }
        [JsonProperty("round_id")] public string round_id { get; set; }
        [JsonProperty("status")] public string status { get; set; }
        [JsonProperty("timer")] public int timer { get; set; }
        [JsonProperty("dice_result")] public int dice_result { get; set; }
        [JsonProperty("dice_values")] public int[] dice_values { get; set; }
        [JsonIgnore] public JObject raw { get; set; }
    }

    [Serializable]
    public class GameEnd
    {
        [JsonProperty("type")]
        public string Type { get; set; }

        [JsonProperty("round_id")]
        public string RoundId { get; set; }

        [JsonProperty("status")]
        public string Status { get; set; }

        [JsonProperty("timer")]
        public int Timer { get; set; }

        [JsonProperty("end_time")]
        public long EndTime { get; set; }

        [JsonProperty("server_time")]
        public long ServerTime { get; set; }

        [JsonProperty("is_rolling")]
        public bool IsRolling { get; set; }

        [JsonProperty("dice_result")]
        public string DiceResult { get; set; }

        [JsonProperty("result")]
        public string Result { get; set; }

        [JsonProperty("dice_values")]
        public int[] DiceValues { get; set; }

        [JsonProperty("dice_1")]
        public int Dice1 { get; set; }

        [JsonProperty("dice_2")]
        public int Dice2 { get; set; }

        [JsonProperty("dice_3")]
        public int Dice3 { get; set; }

        [JsonProperty("dice_4")]
        public int Dice4 { get; set; }

        [JsonProperty("dice_5")]
        public int Dice5 { get; set; }

        [JsonProperty("dice_6")]
        public int Dice6 { get; set; }
    }

    [Serializable]
    public class RoundData
    {
        [JsonProperty("id")]
        public int Id { get; set; }

        [JsonProperty("round_id")]
        public string RoundId { get; set; }

        [JsonProperty("status")]
        public string Status { get; set; } // BETTING, RESULT, etc.

        [JsonProperty("start_time")]
        public DateTime StartTime { get; set; }

        [JsonProperty("timer")]
        public int Timer { get; set; }

        [JsonProperty("dice_result")]
        public int? DiceResult { get; set; }

        [JsonProperty("dice_1")]
        public int? Dice1 { get; set; }

        [JsonProperty("dice_2")]
        public int? Dice2 { get; set; }

        [JsonProperty("dice_3")]
        public int? Dice3 { get; set; }

        [JsonProperty("dice_4")]
        public int? Dice4 { get; set; }

        [JsonProperty("dice_5")]
        public int? Dice5 { get; set; }

        [JsonProperty("dice_6")]
        public int? Dice6 { get; set; }

        [JsonProperty("total_bets")]
        public int TotalBets { get; set; }

        [JsonProperty("total_amount")]
        public string TotalAmount { get; set; }
    }

    [Serializable]
    public class RoundUpdate
    {
        [JsonProperty("type")] public string type { get; set; }
        [JsonProperty("round_id")] public string round_id { get; set; }
        [JsonProperty("status")] public string status { get; set; }
    }

    [Serializable]
    public class MyBet
    {
        [JsonProperty("id")]
        public int id { get; set; }

        [JsonProperty("round")]
        public string round_id { get; set; }

        [JsonProperty("number")]
        public int number { get; set; }

        [JsonProperty("chip_amount")]
        public string chip_amount { get; set; }

        [JsonProperty("is_winner")]
        public bool is_winner { get; set; }

        [JsonProperty("payout_amount")]
        public string payout_amount { get; set; }

        [JsonProperty("created_at")]
        public string created_at { get; set; }
    }

    [Serializable] public class BetRequest { public int number; public string chip_amount; }

    [Serializable]
    public class BetResponse
    {
        public int id;
        public int number;
        public string chip_amount;
        public string created_at;
    }

    [Serializable]
    public class ServerResult
    {
        public string round_id;
        public string status;
        public string message;
    }

    [Serializable]
    public class WinningFrequenceResponse
    {
        [JsonProperty("round_id")]
        public string RoundId { get; set; }

        [JsonProperty("dice_result")]
        public string DiceResult { get; set; }

        [JsonProperty("round")]
        public RoundDetails Round { get; set; }

        [JsonProperty("winning_numbers")]
        public List<WinningNumber> WinningNumbers { get; set; }
    }

    [Serializable]
    public class RoundDetails
    {
        [JsonProperty("round_id")]
        public string RoundId { get; set; }

        [JsonProperty("status")]
        public string Status { get; set; }

        [JsonProperty("dice_result")]
        public string DiceResult { get; set; }

        [JsonProperty("dice_values")]
        public List<int> DiceValues { get; set; }

        [JsonProperty("start_time")]
        public DateTime StartTime { get; set; }

        [JsonProperty("result_time")]
        public DateTime ResultTime { get; set; }

        [JsonProperty("end_time")]
        public DateTime EndTime { get; set; }
    }

    [Serializable]
    public class WinningNumber
    {
        [JsonProperty("number")]
        public int Number { get; set; }

        [JsonProperty("frequency")]
        public int Frequency { get; set; }

        [JsonProperty("payout_multiplier")]
        public float PayoutMultiplier { get; set; }
    }

    [Serializable]
    public class Prediction
    {
        [JsonProperty("id")]
        public int id { get; set; }

        [JsonProperty("user")]
        public User user { get; set; }

        // The backend docs show `round` as integer id
        [JsonProperty("round")]
        public int round { get; set; }

        [JsonProperty("number")]
        public int number { get; set; }

        [JsonProperty("is_correct")]
        public bool is_correct { get; set; }

        [JsonProperty("created_at")]
        public string created_at { get; set; }
    }

    [Serializable]
    public class PredictionResponse
    {
        [JsonProperty("message")]
        public string message { get; set; }

        [JsonProperty("prediction")]
        public Prediction prediction { get; set; }

        /// <summary>Same shape as GET /api/game/round/ — present round state (no extra round call needed).</summary>
        [JsonProperty("round")]
        public JObject round { get; set; }
    }

    [Serializable]
    public class RoundPredictionOverall
    {
        [JsonProperty("total_predictions")]
        public int total_predictions { get; set; }

        [JsonProperty("total_unique_users")]
        public int total_unique_users { get; set; }

        [JsonProperty("total_correct")]
        public int total_correct { get; set; }
    }

    [Serializable]
    public class RoundPredictionByNumber
    {
        [JsonProperty("number")]
        public int number { get; set; }

        [JsonProperty("total_predictions")]
        public int total_predictions { get; set; }

        [JsonProperty("correct_predictions")]
        public int correct_predictions { get; set; }
    }

    [Serializable]
    public class RoundPredictionStatistics
    {
        [JsonProperty("overall")]
        public RoundPredictionOverall overall { get; set; }

        [JsonProperty("by_number")]
        public List<RoundPredictionByNumber> by_number { get; set; }
    }

    [Serializable]
    public class RoundPredictionsResponse
    {
        [JsonProperty("round")]
        public JObject round { get; set; } // keep flexible shape (round_id, status, dice_result)

        [JsonProperty("user_prediction")]
        public Prediction user_prediction { get; set; }

        [JsonProperty("predictions")]
        public List<Prediction> predictions { get; set; }

        [JsonProperty("statistics")]
        public RoundPredictionStatistics statistics { get; set; }

        [JsonProperty("count")]
        public int count { get; set; }
    }

    // --- Additions: Round Bets API models and coroutine ---

    [Serializable]
    public class IndividualBet
    {
        [JsonProperty("id")]
        public int id { get; set; }

        [JsonProperty("user_id")]
        public int user_id { get; set; }

        [JsonProperty("username")]
        public string username { get; set; }

        [JsonProperty("number")]
        public int number { get; set; }

        [JsonProperty("chip_amount")]
        public string chip_amount { get; set; }

        [JsonProperty("created_at")]
        public string created_at { get; set; }

        [JsonProperty("is_winner")]
        public bool is_winner { get; set; }
    }

    [Serializable]
    public class RoundBetsResponse
    {
        [JsonProperty("round")]
        public JObject round { get; set; }

        [JsonProperty("bets")]
        public List<JObject> bets { get; set; } // grouped summary - keep flexible

        [JsonProperty("individual_bets")]
        public List<IndividualBet> individual_bets { get; set; }

        [JsonProperty("statistics")]
        public JObject statistics { get; set; }

        [JsonProperty("count")]
        public int count { get; set; }

        [JsonProperty("individual_count")]
        public int individual_count { get; set; }
    }

    // --- Additions: Round Exposure API models and coroutine ---
    [Serializable]
    public class ExposureEntry
    {
        [JsonProperty("player_id")]
        public int player_id { get; set; }

        [JsonProperty("username")]
        public string username { get; set; }

        // exposure_amount is returned as string by API
        [JsonProperty("exposure_amount")]
        public string exposure_amount { get; set; }
    }

    [Serializable]
    public class RoundExposureResponse
    {
        [JsonProperty("round_id")]
        public string round_id { get; set; }

        [JsonProperty("status")]
        public string status { get; set; }

        [JsonProperty("exposure")]
        public List<ExposureEntry> exposure { get; set; }
    }

    [Serializable]
    public class LoadingTimeResponse
    {
        [JsonProperty("loading_time")]
        public int loading_time { get; set; }
    }

    [Serializable]
    public class SoundSettings
    {
        [JsonProperty("background_music_volume")]
        public float BackgroundMusicVolume { get; set; }

        [JsonProperty("is_muted")]
        public bool IsMuted { get; set; }
    }

    #endregion

    #region Lifecycle & dispatching

    // WebSocket health monitoring
    private float wsStateCheckTimer = 0f;
    private float lastMessageTime = 0f;
    private const float MESSAGE_TIMEOUT = 35f;
    private int dispatchCallCount = 0;

    private void Start()
    {
        Invoke("CheckConnection", 0.75f);
    }

    private void CheckConnection()
    {
        connectionMonitorRoutine = StartCoroutine(ConnectionMonitorLoop());
    }

    private void Update()
    {
        // WebSocket dispatch needs to be called every frame for NativeWebSocket to work reliably.
        if (websocket != null)
        {
            dispatchCallCount++;
            wsStateCheckTimer += Time.deltaTime;

            if (wsStateCheckTimer >= 5f)
            {
                wsStateCheckTimer = 0f;
                dispatchCallCount = 0;

                if (wsConnected && (Time.time - lastMessageTime) > MESSAGE_TIMEOUT)
                {
                    Debug.LogWarning($"[WS TIMEOUT] No messages for {MESSAGE_TIMEOUT}s. Connection may be stale.");
                }
            }

            try
            {
#if !UNITY_WEBGL || UNITY_EDITOR
                websocket.DispatchMessageQueue();
#endif
            }
            catch (Exception ex)
            {
                Debug.LogError("[WS] DispatchMessageQueue error: " + ex.Message);
            }
        }

        // Execute queued main-thread actions
        while (mainThreadQueue.TryDequeue(out var action))
        {
            try { action?.Invoke(); }
            catch (Exception ex) { Debug.LogError("[MainThread] Action error: " + ex.Message); }
        }
    }

    private void OnApplicationQuit() => CloseWebSocket();
    private void OnDestroy()
    {
        // Close websocket safely on destroy
        CloseWebSocket();

        if (connectionMonitorRoutine != null)
            StopCoroutine(connectionMonitorRoutine);
    }


    #endregion

    #region HTTP Coroutines

    private IEnumerator ConnectionMonitorLoop()
    {
        var wait = new WaitForSeconds(connectionCheckInterval);

        while (true)
        {
            bool internetOk = IsInternetAvailable();
            bool serverOk = false;

            if (internetOk)
            {
                yield return StartCoroutine(CheckServerHealth(ok => serverOk = ok));
            }

            //bool wsOk = IsWebSocketHealthy();

            bool shouldShowPopup = !internetOk;//|| !serverOk;//|| !wsOk;

            if (shouldShowPopup && !popupVisible)
            {
                popupVisible = true;

                //string msg =
                //    !internetOk ? "No internet connection" :
                //    !serverOk ? "Server not responding" :
                //    "Connection lost";

                mainThreadQueue.Enqueue(() =>
                {
                    OnShowHidePopup(true);
                });
            }
            else if (!shouldShowPopup && popupVisible)
            {
                popupVisible = false;

                mainThreadQueue.Enqueue(() =>
                {
                    OnShowHidePopup(false);
                    OnReconnect();
                });
            }

            yield return wait;
        }
    }

    private bool IsInternetAvailable()
    {
        return Application.internetReachability != NetworkReachability.NotReachable;
    }

    private IEnumerator CheckServerHealth(Action<bool> callback)
    {
        var url = $"{baseUrl}/api/game/settings/";

        using (var req = UnityWebRequest.Get(url))
        {
            AddAuthHeader(req);
            req.timeout = 5;

            yield return req.SendWebRequest();

#if UNITY_2020_1_OR_NEWER
            bool error = req.result == UnityWebRequest.Result.ConnectionError ||
                         req.result == UnityWebRequest.Result.ProtocolError;
#else
        bool error = req.isNetworkError || req.isHttpError;
#endif

            if (error)
            {
                callback(false);
                yield break;
            }

            callback(true);
        }
    }

    private IEnumerator GetWinningFrequencyCoroutine(Action<bool, WinningFrequenceResponse, string> callback = null)
    {
        var url = $"{baseUrl}/api/game/frequency/";

        using (var req = UnityWebRequest.Get(url))
        {
            AddAuthHeader(req);
            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () =>
                StartCoroutine(GetWinningFrequencyCoroutine(callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError ||
                req.result == UnityWebRequest.Result.ProtocolError)
#else
        if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null,
                    req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var result = JsonConvert.DeserializeObject<WinningFrequenceResponse>(
                    req.downloadHandler.text);

                callback?.Invoke(true, result, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, "JSON Parse Error: " + ex.Message);
            }
        }
    }

    private IEnumerator LoginCoroutine(string username, string password, Action<bool, string> callback = null)
    {
        var url = $"{baseUrl}/api/auth/login/";
        var payload = new Dictionary<string, string>() { { "username", username }, { "password", password } };
        var body = JsonConvert.SerializeObject(payload);

        using (var req = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST))
        {
            var bodyRaw = Encoding.UTF8.GetBytes(body);
            req.uploadHandler = new UploadHandlerRaw(bodyRaw);
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", JSON_CONTENT);

            yield return req.SendWebRequest();

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var auth = JsonConvert.DeserializeObject<AuthResponse>(req.downloadHandler.text);
                accessToken = auth?.access;
                refreshToken = auth?.refresh;
                callback?.Invoke(true, null);

                // Auto-connect websocket after login
                InitWebSocket();

                OnLoginSuccess.Invoke();
                isPlayerLoggedIn = true;
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, ex.Message);
            }
        }
    }

    private IEnumerator RegisterCoroutine(string username, string password, string cnfPassword, Action<bool, RegisterationErrorResponse, string> callback = null)
    {
        var url = $"{baseUrl}/api/auth/register/";
        var payload = new Dictionary<string, string>() { { "username", username }, { "password", password }, { "password2", cnfPassword } };
        var body = JsonConvert.SerializeObject(payload);


        using (var req = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST))
        {
            var bodyRaw = Encoding.UTF8.GetBytes(body);
            req.uploadHandler = new UploadHandlerRaw(bodyRaw);
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", JSON_CONTENT);

            yield return req.SendWebRequest();

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                var registererror = JsonConvert.DeserializeObject<RegisterationErrorResponse>(req.downloadHandler.text);
                callback?.Invoke(false, registererror, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var auth = JsonConvert.DeserializeObject<AuthResponse>(req.downloadHandler.text);
                accessToken = auth?.access;
                refreshToken = auth?.refresh;
                callback?.Invoke(true, null, null);

                // Auto-connect websocket after login
                //InitWebSocket();
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, ex.Message);
            }
        }
    }

    private IEnumerator GetLoadingTimeCoroutine(Action<bool, LoadingTimeResponse, string> callback = null)
    {
        var url = $"{baseUrl}/api/game/loading-time/";
        using (var req = UnityWebRequest.Get(url))
        {
            AddAuthHeader(req);
            yield return req.SendWebRequest();

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var result = JsonConvert.DeserializeObject<LoadingTimeResponse>(req.downloadHandler.text);
                callback?.Invoke(true, result, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, "JSON Parse Error: " + ex.Message);
            }
        }
    }

    private IEnumerator RefreshTokenCoroutine(Action<bool, string> callback = null)
    {
        if (string.IsNullOrEmpty(refreshToken))
        {
            callback?.Invoke(false, "No refresh token available");
            yield break;
        }

        var url = $"{baseUrl}/api/auth/token/refresh/";
        var payload = new Dictionary<string, string>() { { "refresh", refreshToken } };
        var body = JsonConvert.SerializeObject(payload);

        using (var req = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST))
        {
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", JSON_CONTENT);

            yield return req.SendWebRequest();

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var auth = JsonConvert.DeserializeObject<AuthResponse>(req.downloadHandler.text);
                accessToken = auth?.access;
                refreshToken = auth?.refresh;
                callback?.Invoke(true, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, ex.Message);
            }
        }
    }

    private IEnumerator GetPaymentMethodsCoroutine(Action<bool, List<PaymentMethod>, string> callback)
    {
        string url = baseUrl + "/api/auth/payment-methods/";

        using (UnityWebRequest request = UnityWebRequest.Get(url))
        {
            request.SetRequestHeader("Authorization", "Bearer " + accessToken);
            request.SetRequestHeader("Accept", "application/json");

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                callback?.Invoke(false, null, request.error);
                yield break;
            }

            string responseText = request.downloadHandler.text;

            // Safety check
            if (!responseText.Trim().StartsWith("["))
            {
                callback?.Invoke(false, null, "Invalid JSON response");
                yield break;
            }

            try
            {
                List<PaymentMethod> methods =
                    JsonConvert.DeserializeObject<List<PaymentMethod>>(responseText);

                callback?.Invoke(true, methods, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, ex.Message);
            }
        }
    }

    private IEnumerator GetRoundExposureCoroutine(string roundId, int? userId, Action<bool, RoundExposureResponse, string> callback = null)
    {
        // Support both: /api/game/round/exposure/  and /api/game/round/{roundId}/exposure/
        string url;
        if (!string.IsNullOrEmpty(roundId))
            url = $"{baseUrl}/api/game/round/{UnityWebRequest.EscapeURL(roundId)}/exposure/";
        else
            url = $"{baseUrl}/api/game/round/exposure/";

        // append user_id query if provided and not already present
        if (userId.HasValue)
        {
            // if url already has ? keep & else ?
            url += (url.Contains("?") ? "&" : "?") + "user_id=" + userId.Value;
        }

        using (var req = UnityWebRequest.Get(url))
        {
            // Public endpoint: no auth required but adding auth header won't hurt if available
            AddAuthHeader(req);
            yield return req.SendWebRequest();

            // No auth-retry behavior (public) but still handle 401 via existing helper
            if (HandleAuthErrors(req, () => StartCoroutine(GetRoundExposureCoroutine(roundId, userId, callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler?.text);
                yield break;
            }

            var text = req.downloadHandler != null ? req.downloadHandler.text : null;
            if (string.IsNullOrEmpty(text))
            {
                callback?.Invoke(false, null, "Empty response from server");
                yield break;
            }

            try
            {
                var resp = JsonConvert.DeserializeObject<RoundExposureResponse>(text);
                callback?.Invoke(true, resp, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, "JSON Parse Error: " + ex.Message);
            }
        }
    }

    private IEnumerator UploadDepositProofCoroutine(
    string amount,
    byte[] screenshotBytes,
    string screenshotFileName,
    string paymentLink = null,
    string paymentReference = null,
    Action<bool, DepositProofResponse, string> callback = null)
    {
        string url = $"{baseUrl}/api/auth/deposits/upload-proof/";

        WWWForm form = new WWWForm();
        form.AddField("amount", amount);

        if (!string.IsNullOrEmpty(paymentLink))
            form.AddField("payment_link", paymentLink);

        if (!string.IsNullOrEmpty(paymentReference))
            form.AddField("payment_reference", paymentReference);

        // IMPORTANT: file field name must be "screenshot"
        form.AddBinaryData(
            "screenshot",
            screenshotBytes,
            screenshotFileName,
            "image/jpeg"   // or image/png based on your screenshot
        );

        using (UnityWebRequest req = UnityWebRequest.Post(url, form))
        {
            AddAuthHeader(req); // adds Bearer token automatically
            req.timeout = 15;

            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () =>
                StartCoroutine(UploadDepositProofCoroutine(
                    amount,
                    screenshotBytes,
                    screenshotFileName,
                    paymentLink,
                    paymentReference,
                    callback))))
            {
                yield break;
            }

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError ||
                req.result == UnityWebRequest.Result.ProtocolError)
#else
        if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null,
                    req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var response =
                    JsonConvert.DeserializeObject<DepositProofResponse>(
                        req.downloadHandler.text);

                callback?.Invoke(true, response, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, "JSON Parse Error: " + ex.Message);
            }
        }
    }

    private IEnumerator GetWalletCoroutine(Action<bool, WalletResponse, string> callback = null)
    {
        var url = $"{baseUrl}/api/auth/wallet/";
        using (var req = UnityWebRequest.Get(url))
        {
            AddAuthHeader(req);
            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(GetWalletCoroutine(callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var wallet = JsonConvert.DeserializeObject<WalletResponse>(req.downloadHandler.text);
                callback?.Invoke(true, wallet, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, ex.Message);
            }
        }
    }

    private IEnumerator GetBetAmountSummaryCoroutine(Action<bool, List<BetAmountSummary>, string> callback = null)
    {
        var url = $"{baseUrl}/api/game/user-bets-summary/";
        using (var req = UnityWebRequest.Get(url))
        {
            AddAuthHeader(req);
            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(GetBetAmountSummaryCoroutine(callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var betAmtSummary = JsonConvert.DeserializeObject<List<BetAmountSummary>>(req.downloadHandler.text);
                callback?.Invoke(true, betAmtSummary, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, ex.Message);
            }
        }
    }

    private IEnumerator GetMaxBetAmountCoroutine(Action<bool, MaxBetResponse, string> callback = null)
    {
        var url = $"{baseUrl}/api/game/max-bet/";
        using (var req = UnityWebRequest.Get(url))
        {
            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(GetMaxBetAmountCoroutine(callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var maxBetResponse = JsonConvert.DeserializeObject<MaxBetResponse>(req.downloadHandler.text);
                callback?.Invoke(true, maxBetResponse, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, ex.Message);
            }
        }
    }

    private IEnumerator GetGameSettingCoroutine(Action<bool, GameSettings, string> callback = null)
    {
        var url = $"{baseUrl}/api/game/settings/";
        using (var req = UnityWebRequest.Get(url))
        {
            AddAuthHeader(req);
            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(GetGameSettingCoroutine(callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var settings = JsonConvert.DeserializeObject<GameSettings>(req.downloadHandler.text);
                callback?.Invoke(true, settings, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, ex.Message);
            }
        }
    }

    private IEnumerator GetCurrentRoundResultCoroutine(Action<bool, RoundResultResponse, string> callback = null)
    {
        var url = $"{baseUrl}/api/game/winning-results/";

        using (var req = UnityWebRequest.Get(url))
        {
            AddAuthHeader(req);

            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(GetCurrentRoundResultCoroutine(callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError ||
                req.result == UnityWebRequest.Result.ProtocolError)
#else
        if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            if (req.downloadHandler == null)
            {
                callback?.Invoke(false, null, "DownloadHandler is null");
                yield break;
            }

            try
            {
                var json = req.downloadHandler.text;
                Debug.Log("Winning Result Response: " + json);

                if (string.IsNullOrEmpty(json))
                {
                    callback?.Invoke(false, null, "Empty response");
                    yield break;
                }

                var roundResult = JsonConvert.DeserializeObject<RoundResultResponse>(json);

                callback?.Invoke(true, roundResult, null);
            }
            catch (Exception ex)
            {
                Debug.LogError("Deserialization Error: " + ex);
                callback?.Invoke(false, null, ex.Message);
            }
        }
    }


    private IEnumerator GetLastRoundResultsCoroutine(Action<bool, LastRoundResult, string> callback = null)
    {
        string url = $"{baseUrl}/api/game/last-round-results/";

        using (UnityWebRequest req = UnityWebRequest.Get(url))
        {
            req.SetRequestHeader("Content-Type", "application/json");
            AddAuthHeader(req);

            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () =>
                StartCoroutine(GetLastRoundResultsCoroutine(callback))))
            {
                yield break;
            }

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError ||
                req.result == UnityWebRequest.Result.ProtocolError)
#else
        if (req.isNetworkError || req.isHttpError)
#endif
            {
                string errorMsg = $"Error: {req.error}\nResponse: {req.downloadHandler.text}";
                Debug.LogError(errorMsg);
                callback?.Invoke(false, null, errorMsg);
                yield break;
            }

            try
            {
                var result = JsonConvert.DeserializeObject<LastRoundResult>(
                    req.downloadHandler.text);

                callback?.Invoke(true, result, null);
            }
            catch (Exception ex)
            {
                Debug.LogError("JSON Parse Error: " + ex.Message);
                callback?.Invoke(false, null, ex.Message);
            }
        }
    }

    private IEnumerator GetRoundCoroutine(Action<bool, RoundData, string> callback = null)
    {
        var url = $"{baseUrl}/api/game/round/";
        using (var req = UnityWebRequest.Get(url))
        {
            AddAuthHeader(req);
            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(GetRoundCoroutine(callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var data = JsonConvert.DeserializeObject<RoundData>(req.downloadHandler.text);
                callback?.Invoke(true, data, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, ex.Message);
            }
        }
    }

    private IEnumerator PlaceBetCoroutine(int number, float amount, Action<bool, BetResponse, string> callback = null)
    {
        var url = $"{baseUrl}/api/game/bet/";
        var br = new BetRequest() { number = number, chip_amount = amount.ToString("F2") };
        var body = JsonConvert.SerializeObject(br);

        using (var req = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST))
        {
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", JSON_CONTENT);
            AddAuthHeader(req);

            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(PlaceBetCoroutine(number, amount, callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var res = JsonConvert.DeserializeObject<BetResponse>(req.downloadHandler.text);
                callback?.Invoke(true, res, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, ex.Message);
            }
        }
    }

    private IEnumerator DeleteBetCoroutine(int number, Action<bool, string> callback = null)
    {
        var url = $"{baseUrl}/api/game/bet/{number}/";
        using (var req = UnityWebRequest.Delete(url))
        {
            AddAuthHeader(req);
            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(DeleteBetCoroutine(number, callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            callback?.Invoke(true, null);
        }
    }

    private IEnumerator DeleteLastBetCoroutine(Action<bool, string> callback = null)
    {
        // Endpoint from provided API docs
        var url = $"{baseUrl}/api/game/bet/last/";

        using (var req = UnityWebRequest.Delete(url))
        {
            // Ensure request headers
            req.SetRequestHeader("Content-Type", "application/json");
            AddAuthHeader(req); // reuses existing method to attach Authorization header

            yield return req.SendWebRequest();

            // If HandleAuthErrors triggers a retry (e.g. token refresh), it will re-run this coroutine.
            if (HandleAuthErrors(req, () => StartCoroutine(DeleteLastBetCoroutine(callback))))
            {
                yield break;
            }

#if UNITY_2020_1_OR_NEWER
            bool hasError = req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError;
#else
            bool hasError = req.isNetworkError || req.isHttpError;
#endif
            if (hasError)
            {
                string errText = req.downloadHandler != null ? req.downloadHandler.text : req.error;
                callback?.Invoke(false, errText);
                yield break;
            }

            callback?.Invoke(true, null);
        }
    }

    private IEnumerator SubmitPredictionCoroutine(int number, Action<bool, PredictionResponse, string> callback = null)
    {
        var url = $"{baseUrl}/api/game/prediction/";
        var payload = new { number = number };
        var body = JsonConvert.SerializeObject(payload);

        using (var req = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST))
        {
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", JSON_CONTENT);
            AddAuthHeader(req);

            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(SubmitPredictionCoroutine(number, callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                var err = req.downloadHandler != null ? req.downloadHandler.text : req.error;
                callback?.Invoke(false, null, req.error + " : " + err);
                yield break;
            }

            var text = req.downloadHandler != null ? req.downloadHandler.text : null;
            if (string.IsNullOrEmpty(text))
            {
                callback?.Invoke(false, null, "Empty response from server");
                yield break;
            }

            try
            {
                var resp = JsonConvert.DeserializeObject<PredictionResponse>(text);
                callback?.Invoke(true, resp, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, "JSON Parse Error: " + ex.Message);
            }
        }
    }

    /// <summary>
    /// GET /api/game/round/predictions/ — server resolves the current round (no round_id in URL).
    /// </summary>
    private IEnumerator GetRoundPredictionsCoroutine(string roundId, Action<bool, RoundPredictionsResponse, string> callback = null)
    {
        string url;
        if (string.IsNullOrEmpty(roundId))
            url = $"{baseUrl}/api/game/round/predictions/";
        else
            url = $"{baseUrl}/api/game/round/{UnityWebRequest.EscapeURL(roundId)}/predictions/";

        using (var req = UnityWebRequest.Get(url))
        {
            AddAuthHeader(req);
            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(GetRoundPredictionsCoroutine(roundId, callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler.text);
                yield break;
            }

            try
            {
                var resp = JsonConvert.DeserializeObject<RoundPredictionsResponse>(req.downloadHandler.text);
                callback?.Invoke(true, resp, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, "JSON Parse Error: " + ex.Message);
            }
        }
    }

    private IEnumerator GetRoundBetsCoroutine(string roundId, Action<bool, RoundBetsResponse, string> callback = null)
    {
        string url = $"{baseUrl}/api/game/round/bets/";
        if (!string.IsNullOrEmpty(roundId))
        {
            // append as query param
            url += $"?round_id={UnityWebRequest.EscapeURL(roundId)}";
        }

        using (var req = UnityWebRequest.Get(url))
        {
            AddAuthHeader(req);
            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(GetRoundBetsCoroutine(roundId, callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler?.text);
                yield break;
            }

            try
            {
                var resp = JsonConvert.DeserializeObject<RoundBetsResponse>(req.downloadHandler.text);
                callback?.Invoke(true, resp, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, "JSON Parse Error: " + ex.Message);
            }
        }
    }

    private IEnumerator GetSoundSettingsCoroutine(Action<bool, SoundSettings, string> callback = null)
    {
        var url = $"{baseUrl}/api/game/settings/sound/";
        using (var req = UnityWebRequest.Get(url))
        {
            AddAuthHeader(req);
            yield return req.SendWebRequest();

            if (HandleAuthErrors(req, () => StartCoroutine(GetSoundSettingsCoroutine(callback))))
                yield break;

#if UNITY_2020_1_OR_NEWER
            if (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                callback?.Invoke(false, null, req.error + " : " + req.downloadHandler?.text);
                yield break;
            }

            try
            {
                var settings = JsonConvert.DeserializeObject<SoundSettings>(req.downloadHandler.text);
                callback?.Invoke(true, settings, null);
            }
            catch (Exception ex)
            {
                callback?.Invoke(false, null, "JSON Parse Error: " + ex.Message);
            }
        }
    }

    #endregion

    #region WebSocket (NativeWebSocket)

    /// <summary>
    /// Initialize WebSocket connection. If accessToken is present, attach as ?token=... parameter.
    /// Uses stored delegates so they can be removed cleanly on close.
    /// </summary>
    public async void InitWebSocket()
    {
        // ensure previous connection closed and handlers removed
        try
        {
            await CloseWebSocketAsync(); // helper below to do a clean synchronous close
        }
        catch { /* ignore */ }

        try
        {
            var wsFull = wsUrl;
            if (!string.IsNullOrEmpty(accessToken))
            {
                wsFull = wsUrl.EndsWith("/") ? wsUrl + "?token=" + accessToken : wsUrl + "?token=" + accessToken;
                DebugLog("[WS] Connecting with token");
            }
            else
            {
                DebugLog("[WS] Connecting without token (public mode)");
            }

            websocket = new WebSocket(wsFull);

            // prepare stored delegates so we can remove them later
            wsOnOpen = () =>
            {
                wsConnected = true;
                mainThreadQueue.Enqueue(() =>
                {
                    DebugLog("[WS] Connected");
                    OnConnected?.Invoke();

                    // quick sanity messages
                    SendWebSocketMessage(new { type = "ping" });
                    SendWebSocketMessage(new { type = "get_state" });
                });
            };

            wsOnClose = (code) =>
            {
                wsConnected = false;
                mainThreadQueue.Enqueue(() =>
                {
                    DebugLog($"[WS] Closed (code {code})");
                    OnDisconnected?.Invoke();
                });
            };

            wsOnError = (err) =>
            {
                mainThreadQueue.Enqueue(() =>
                {
                    Debug.LogError("[WS] Error: " + err);
                    OnError?.Invoke(err);
                });
            };

            wsOnMessage = (bytes) =>
            {
                // bytes arrive on background thread -> marshal to main thread
                string msg = Encoding.UTF8.GetString(bytes);
                DebugLog($"[WS RAW] Received {bytes.Length} bytes: {msg}");
                DebugLog($"[WS RAW] Time: {DateTime.Now:HH:mm:ss.fff}");

                mainThreadQueue.Enqueue(() => HandleWsMessage(msg));
            };

            // Attach handlers
            websocket.OnOpen += wsOnOpen;
            websocket.OnClose += wsOnClose;
            websocket.OnError += wsOnError;
            websocket.OnMessage += wsOnMessage;

            DebugLog($"[WS] Connecting to: {wsFull}");
            await websocket.Connect();
        }
        catch (Exception ex)
        {
            Debug.LogError("[WS] Init exception: " + ex.Message);
            OnError?.Invoke(ex.Message);
        }
    }

    public async void CloseWebSocket()
    {
        try
        {
            await CloseWebSocketAsync();
        }
        catch (Exception ex)
        {
            Debug.LogWarning("[WS] CloseWebSocket error: " + ex.Message);
        }
        finally
        {
            wsConnected = false;
        }
    }

    // New helper to close and cleanup websocket safely (used by Init and OnDestroy)
    private async System.Threading.Tasks.Task CloseWebSocketAsync()
    {
        if (websocket == null) return;

        try
        {
            // Detach handlers first to avoid native callback into disposed managed objects
            try
            {
                if (wsOnOpen != null) websocket.OnOpen -= wsOnOpen;
                if (wsOnClose != null) websocket.OnClose -= wsOnClose;
                if (wsOnError != null) websocket.OnError -= wsOnError;
                if (wsOnMessage != null) websocket.OnMessage -= wsOnMessage;
            }
            catch { /* some transports might throw on -=; ignore safely */ }

            // Close the websocket connection
            await websocket.Close();
        }
        catch (Exception ex)
        {
            Debug.LogWarning("[WS] CloseWebSocketAsync exception: " + ex.Message);
        }
        finally
        {
            // ensure references removed
            try
            {
                websocket = null;
            }
            catch { }
            wsOnOpen = null;
            wsOnClose = null;
            wsOnError = null;
            wsOnMessage = null;
        }
    }

    /// <summary>
    /// Sends a JSON-serializable object over WebSocket if open.
    /// </summary>
    public void SendWebSocketMessage(object obj)
    {
        if (websocket == null || websocket.State != WebSocketState.Open)
        {
            Debug.LogWarning($"[WS] Not ready. State: {websocket?.State}");
            return;
        }

        try
        {
            string msg = JsonConvert.SerializeObject(obj);
            DebugLog("[WS SEND] " + msg);
            _ = websocket.SendText(msg);
        }
        catch (Exception ex)
        {
            Debug.LogError("[WS] Send error: " + ex.Message);
        }
    }

    private void HandleWsMessage(string json)
    {
        if (string.IsNullOrEmpty(json)) return;
        lastMessageTime = Time.time;

        try
        {
            var j = JObject.Parse(json);
            if (!j.ContainsKey("type"))
            {
                Debug.LogWarning("[WS] Message without 'type': " + json);
                return;
            }

            string type = j["type"].ToString().ToLowerInvariant();

            switch (type)
            {
                case "game_state":
                    {
                        var msg = j.ToObject<GameState>();
                        OnGameState?.Invoke(msg);
                        break;
                    }
                case "timer":
                    {
                        var msg = j.ToObject<TimerUpdate>();
                        OnTimerUpdate?.Invoke(msg);
                        break;
                    }
                case "game_start":
                    {
                        var msg = j.ToObject<GameStart>();
                        OnGameStart?.Invoke(msg);
                        break;
                    }
                case "dice_roll":
                    {
                        var msg = j.ToObject<DiceRollWarning>();
                        OnDiceRollWarn?.Invoke(msg);
                        break;
                    }
                case "dice_result":
                    {
                        var msg = j.ToObject<DiceResult>();
                        OnDiceResult?.Invoke(msg);
                        break;
                    }
                case "result":
                    {
                        var msg = j.ToObject<ResultAnnouncement>();
                        msg.raw = j;
                        OnResultAnn?.Invoke(msg);
                        break;
                    }
                case "game_end":
                    {
                        var msg = j.ToObject<GameEnd>();
                        OnGameEnd?.Invoke(msg);
                        break;
                    }
                case "round_update":
                    {
                        var msg = j.ToObject<RoundUpdate>();
                        OnRoundUpdate?.Invoke(msg);
                        break;
                    }
                default:
                    {
                        Debug.LogWarning($"[WS] Unhandled type '{type}': {json}");
                        break;
                    }
            }
        }
        catch (Exception ex)
        {
            Debug.LogError($"[WS] HandleWsMessage parse error: {ex.Message}\nRaw: {json}");
        }
    }

    #endregion

    #region Helpers

    private void AddAuthHeader(UnityWebRequest req)
    {
        if (!string.IsNullOrEmpty(accessToken))
            req.SetRequestHeader("Authorization", "Bearer " + accessToken);
    }

    /// <summary>
    /// If response indicates auth error (401) attempt refresh and then retry original action via provided delegate.
    /// Returns true if caller should abort (because refresh coroutine handled the retry), false otherwise.
    /// </summary>
    private bool HandleAuthErrors(UnityWebRequest req, Action retryAction)
    {
#if UNITY_2020_1_OR_NEWER
        bool isError = (req.result == UnityWebRequest.Result.ConnectionError || req.result == UnityWebRequest.Result.ProtocolError);
#else
        bool isError = (req.isNetworkError || req.isHttpError);
#endif
        if (!isError) return false;

        long code = req.responseCode;
        if (code == 401)
        {
            // attempt refresh once, then call retryAction if successful
            StartCoroutine(RefreshTokenCoroutine((ok, msg) =>
            {
                if (ok)
                {
                    retryAction?.Invoke();
                }
                else
                {
                    Debug.LogWarning("[Auth] Refresh failed: " + msg);
                    mainThreadQueue.Enqueue(() => OnError?.Invoke("Session expired. Please login again."));
                }
            }));
            return true;
        }
        return false;
    }

    /// <summary>
    /// Simple debug wrapper to reduce verbosity in code.
    /// </summary>
    private void DebugLog(string msg)
    {
        //Debug.Log($"[GameApiClient] {msg}");
    }

    #endregion

    #region Convenience wrappers

    public void Register(string username, string password, string cnfPassword, Action<bool, RegisterationErrorResponse, string> callback = null) =>
        StartCoroutine(RegisterCoroutine(username, password, cnfPassword, callback));

    public void Login(string username, string password, Action<bool, string> callback = null) =>
        StartCoroutine(LoginCoroutine(username, password, callback));

    public void GetLoadingTime(Action<bool, LoadingTimeResponse, string> callback = null) =>
        StartCoroutine(GetLoadingTimeCoroutine(callback));

    public void RefreshToken(Action<bool, string> callback = null) =>
        StartCoroutine(RefreshTokenCoroutine(callback));

    public void GetPaymentMethods(Action<bool, List<PaymentMethod>, string> callback = null) =>
        StartCoroutine(GetPaymentMethodsCoroutine(callback));

    public void DeleteLastBet(Action<bool, string> callback = null) =>
        StartCoroutine(DeleteLastBetCoroutine(callback));

    public void UploadDepositProof(string amount, byte[] screenshotBytes, string screenshotFileName, string paymentLink = null,
    string paymentReference = null, Action<bool, DepositProofResponse, string> callback = null) =>
        StartCoroutine(UploadDepositProofCoroutine(amount, screenshotBytes, screenshotFileName, paymentLink,
                                                   paymentReference, callback));

    public void GetGameSettings(Action<bool, GameSettings, string> callback = null) =>
       StartCoroutine(GetGameSettingCoroutine(callback));

    public void GetCurrentRoundResult(Action<bool, RoundResultResponse, string> callback = null) =>
       StartCoroutine(GetCurrentRoundResultCoroutine(callback));

    public void GetLastRoundResult(Action<bool, LastRoundResult, string> callback = null) =>
      StartCoroutine(GetLastRoundResultsCoroutine(callback));

    public void GetWallet(Action<bool, WalletResponse, string> callback = null) =>
        StartCoroutine(GetWalletCoroutine(callback));

    public void GetBetAmountSummary(Action<bool, List<BetAmountSummary>, string> callback = null) =>
        StartCoroutine(GetBetAmountSummaryCoroutine(callback));

    public void GetMaxBetAmountSummary(Action<bool, MaxBetResponse, string> callback = null) =>
        StartCoroutine(GetMaxBetAmountCoroutine(callback));

    public void GetCurrentRound(Action<bool, RoundData, string> callback = null) =>
        StartCoroutine(GetRoundCoroutine(callback));

    public void PlaceBet(int number, float amount, Action<bool, BetResponse, string> callback = null) =>
        StartCoroutine(PlaceBetCoroutine(number, amount, callback));

    public void DeleteBet(int number, Action<bool, string> callback = null) =>
        StartCoroutine(DeleteBetCoroutine(number, callback));

    public void GetWinningFrequency(Action<bool, WinningFrequenceResponse, string> callback = null) =>
        StartCoroutine(GetWinningFrequencyCoroutine(callback));

    public void SubmitPrediction(int number, Action<bool, PredictionResponse, string> callback = null) =>
        StartCoroutine(SubmitPredictionCoroutine(number, callback));

    /// <summary>Fetch predictions for the current round — no round_id required.</summary>
    public void GetRoundPredictions(Action<bool, RoundPredictionsResponse, string> callback = null) =>
        StartCoroutine(GetRoundPredictionsCoroutine(null, callback));

    /// <summary>Optional: fetch predictions for a specific round by id (historic/debug).</summary>
    public void GetRoundPredictionsForRound(string roundId, Action<bool, RoundPredictionsResponse, string> callback = null) =>
        StartCoroutine(GetRoundPredictionsCoroutine(roundId, callback));

    public void GetRoundBets(string roundId, Action<bool, RoundBetsResponse, string> callback = null) =>
        StartCoroutine(GetRoundBetsCoroutine(roundId, callback));

    public void GetRoundExposure(string roundId, int? userId, Action<bool, RoundExposureResponse, string> callback = null) =>
        StartCoroutine(GetRoundExposureCoroutine(roundId, userId, callback));

    public void GetSoundSettings(Action<bool, SoundSettings, string> callback = null) =>
        StartCoroutine(GetSoundSettingsCoroutine(callback));

    public void ReconnectWebSocket()
    {
        DebugLog("[WS] Manual reconnect requested");
        InitWebSocket();
    }

    public bool IsWebSocketHealthy()
    {
        if (isPlayerLoggedIn == false) return true;
        if (websocket == null) return false;
        if (!wsConnected) return false;
        if (websocket.State != WebSocketState.Open) return false;
        if ((Time.time - lastMessageTime) > MESSAGE_TIMEOUT) return false;
        return true;
    }

    #endregion

    // --- Caching wrappers ---

    // Use this instead of direct GetCurrentRound when you expect repeated calls
    public void GetCurrentRoundCached(Action<bool, RoundData, string> callback = null)
    {
        if (cachedRoundData != null && (Time.time - cachedRoundTimestamp) < ROUND_CACHE_TTL)
        {
            callback?.Invoke(true, cachedRoundData, null);
            return;
        }

        StartCoroutine(GetRoundCoroutine((ok, data, err) =>
        {
            if (ok && data != null)
            {
                cachedRoundData = data;
                cachedRoundTimestamp = Time.time;
            }
            callback?.Invoke(ok, data, err);
        }));
    }

    // Use this instead of direct GetGameSettings when you expect repeated calls
    public void GetGameSettingsCached(Action<bool, GameSettings, string> callback = null)
    {
        if (cachedGameSettings != null && (Time.time - cachedSettingsTimestamp) < SETTINGS_CACHE_TTL)
        {
            callback?.Invoke(true, cachedGameSettings, null);
            return;
        }

        StartCoroutine(GetGameSettingCoroutine((ok, settings, err) =>
        {
            if (ok && settings != null)
            {
                cachedGameSettings = settings;
                cachedSettingsTimestamp = Time.time;
            }
            callback?.Invoke(ok, settings, err);
        }));
    }

    public void SetAccessAndRefreshToken(string accessToken, string refreshToken)
    {
        this.accessToken = accessToken;
        this.refreshToken = refreshToken;
        InitWebSocket();
        OnLoginSuccess.Invoke();
        isPlayerLoggedIn = true;
    }

    // Optional: invalidate caches when you know state changed (call when websocket announces new round/state)
    private void InvalidateCaches()
    {
        cachedRoundData = null;
        cachedRoundTimestamp = 0f;
        // keep settings longer, but you can invalidate too if required
    }
}