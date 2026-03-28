using System;
using System.Collections.Generic;
using UnityEngine;
using static GameApiClient;

[Serializable]
public class TokenData
{
    public string accessToken;
    public string refreshToken;
}

[Serializable]
public class UserData
{
    public string username;
    public string password;
}

public class GameManager : MonoBehaviour
{
    public static GameManager Instance { get; private set; }

    [Header("API")]
    [SerializeField] private GameApiClient apiClient;

    public GameApiClient ApiClient => apiClient;

    public float WalletAmount { get; private set; }
    public GameSettings GameSettings { get; private set; }
    public Action<float> OnWalletUpdated;

    public int loadingTime { get; private set; }

    private Action onInitializationCompelete;

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
        onInitializationCompelete?.Invoke();
    }

    private void OnDestroy()
    {
        PlayerPrefs.DeleteAll();
    }

    private void OnApplicationQuit()
    {
        PlayerPrefs.DeleteAll();
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

    public void SetAccessAndRefreshToken(string json)
    {
        onInitializationCompelete += () =>
        {
            TokenData data = JsonUtility.FromJson<TokenData>(json);
            PlayerPrefs.SetString("accessToken", data.accessToken);
            PlayerPrefs.SetString("refreshToken", data.refreshToken);
            PlayerPrefs.Save();
            UIManager.Instance.AutoLoginIfPossible();
        };
    }

    public void SetLoginCredential(string json)
    {
        onInitializationCompelete += () =>
        {
            UserData data = JsonUtility.FromJson<UserData>(json);
            PlayerPrefs.SetString("username", data.username);
            PlayerPrefs.SetString("password", data.password);
            PlayerPrefs.Save();
            UIManager.Instance.AutoLoginIfPossible();
        };
    }
}