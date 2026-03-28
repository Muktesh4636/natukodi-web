using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Attach this to any back Button (e.g. top-left in game). On click, returns to Kotlin app home.
/// Alternatively assign the back button to GameplayUIManager.backButton.
/// </summary>
[RequireComponent(typeof(Button))]
public class BackToKotlinButton : MonoBehaviour
{
    private Button _webglOverlay;

    private void Awake()
    {
        var btn = GetComponent<Button>();
        if (btn == null) return;
        _webglOverlay = WebGLBackButtonHelper.InstallLargeHitOverlayIfNeeded(btn, BackToKotlin.GoBackToKotlin);
        if (_webglOverlay == null)
            btn.onClick.AddListener(BackToKotlin.GoBackToKotlin);
    }

    private void OnDestroy()
    {
        if (_webglOverlay != null)
            _webglOverlay.onClick.RemoveListener(BackToKotlin.GoBackToKotlin);
        else
        {
            var b = GetComponent<Button>();
            if (b != null) b.onClick.RemoveListener(BackToKotlin.GoBackToKotlin);
        }
    }
}
