using UnityEngine;

public static class AndroidToast
{
    public static void Show(string message, bool isLong = false)
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        using (AndroidJavaClass toastClass =
               new AndroidJavaClass("com.yourcompany.toast.ToastPlugin"))
        {
            toastClass.CallStatic("showToast", message, isLong);
        }
#else
        Debug.Log("[Toast] " + message);
#endif
    }
}