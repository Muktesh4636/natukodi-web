using System;
using System.Collections.Generic;
using UnityEngine;
using static GameApiClient;

public class GameManager : MonoBehaviour
{
    public static GameManager Instance { get; private set; }

    [Header("API")]
    [SerializeField] private GameApiClient apiClient;

    public GameApiClient ApiClient => apiClient;

    public float WalletAmount { get; private set; }
    public GameSettings GameSettings { get; private set; }
    public Action<float> OnWalletUpdated;

    public int loadingTime {get; private set; }

    private void Awake()
    {
        Application.targetFrameRate = 60;
        loadingTime = 8; // Default loading time, will be updated from server
        if (Instance != null)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;
        DontDestroyOnLoad(gameObject);
    }

    private void Start()
    {
        ApiClient.OnLoginSuccess += FetchInitialData;
        ApiClient.GetLoadingTime((ok, time, err) =>
        {
            if (ok)
                loadingTime = time.loading_time;
        });
        ApiClient.GetSoundSettings((ok, settings, err) =>
        {
            if (ok && settings != null)
                AudioManager.Instance.SetBackgroundMusicVolume(settings.BackgroundMusicVolume);
        });
        UIManager.Instance.AutoLoginIfPossible();
    }

    private void FetchInitialData()
    {
        apiClient.GetGameSettings((ok, settings, err) =>
        {
            if (ok && settings != null)
                GameSettings = settings;
        });

        RefreshWallet();
    }

    public void RefreshWallet()
    {
        apiClient.GetWallet((ok, wallet, err) =>
        {
            if (ok && wallet != null)
            {
                WalletAmount = float.Parse(wallet.balance);
                OnWalletUpdated?.Invoke(WalletAmount);
            }
        });
    }

    // 🔒 Future-ready
    // public void RegisterUser(...) {}
    // public void Deposit(...) {}
}