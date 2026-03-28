using System.Runtime.InteropServices;
using UnityEngine;

/// <summary>
/// Call this when the user taps the in-game back button to return to the Kotlin app (home) or website homepage (WebGL).
/// </summary>
public static class BackToKotlin
{
#if UNITY_WEBGL && !UNITY_EDITOR
    [DllImport("__Internal")]
    private static extern void GoToHomepage();
#endif

    public static void GoBackToKotlin()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        try
        {
            using (var unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
            using (var activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity"))
            {
                if (activity != null)
                    activity.Call("goBackToKotlin");
            }
        }
        catch (System.Exception e)
        {
            Debug.LogWarning("BackToKotlin: " + e.Message);
        }
#elif UNITY_WEBGL && !UNITY_EDITOR
        GoToHomepage();
#else
        Debug.Log("[BackToKotlin] Would return to Kotlin (Android only) or homepage (WebGL)");
#endif
    }
}
