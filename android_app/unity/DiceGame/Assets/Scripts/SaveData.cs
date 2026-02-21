using System;
using UnityEngine;

public static class SaveData
{
    private const string USERNAME_KEY = "username";
    private const string PASSWORD_KEY = "password";
    private const string BET_ROUND_ID_KEY = "betRoundID";
    private const string BET_NUMBER_KEY = "betNumber";

    #region Auth

    public static void SaveUsername(string username)
    {
        PlayerPrefs.SetString(USERNAME_KEY, username);
        PlayerPrefs.Save();
    }

    public static void SavePassword(string password)
    {
        PlayerPrefs.SetString(PASSWORD_KEY, password);
        PlayerPrefs.Save();
    }

    public static string GetUsername()
    {
        return PlayerPrefs.GetString(USERNAME_KEY, string.Empty);
    }

    public static string GetPassword()
    {
        return PlayerPrefs.GetString(PASSWORD_KEY, string.Empty);
    }

    #endregion
}
