using UnityEngine;
using UnityEngine.Events;
using UnityEngine.UI;

/// <summary>
/// WebGL: Unity's visible back icon is often too small to tap. Adds a transparent sibling button
/// with a larger rect so taps reliably go to <see cref="BackToKotlin.GoBackToKotlin"/> (homepage).
/// </summary>
public static class WebGLBackButtonHelper
{
    /// <summary>Padding beyond the original button rect on each side (pixels in canvas space).</summary>
    public const float ExpandEachSide = 48f;

    /// <summary>Minimum width/height for the hit area (accessibility).</summary>
    public const float MinTouchSide = 132f;

    /// <summary>
    /// On WebGL builds, disables raycast on the original graphic and adds a larger transparent button on top.
    /// Returns the overlay button for lifecycle cleanup, or null when not used.
    /// </summary>
    public static Button InstallLargeHitOverlayIfNeeded(Button originalBackButton, UnityAction onClick)
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        return InstallLargeHitOverlay(originalBackButton, onClick);
#else
        return null;
#endif
    }

#if UNITY_WEBGL && !UNITY_EDITOR
    private static Button InstallLargeHitOverlay(Button originalBackButton, UnityAction onClick)
    {
        if (originalBackButton == null || onClick == null) return null;

        var targetRt = originalBackButton.transform as RectTransform;
        if (targetRt == null) return null;

        if (originalBackButton.targetGraphic is Graphic g)
            g.raycastTarget = false;

        originalBackButton.transition = Selectable.Transition.None;

        var go = new GameObject("WebGL_BackHitOverlay", typeof(RectTransform));
        var rt = go.GetComponent<RectTransform>();
        var parent = targetRt.parent as RectTransform;
        go.transform.SetParent(parent, false);

        rt.anchorMin = targetRt.anchorMin;
        rt.anchorMax = targetRt.anchorMax;
        rt.pivot = targetRt.pivot;
        rt.anchoredPosition = targetRt.anchoredPosition;
        rt.localRotation = targetRt.localRotation;
        rt.localScale = targetRt.localScale;

        float w = targetRt.sizeDelta.x + ExpandEachSide * 2f;
        float h = targetRt.sizeDelta.y + ExpandEachSide * 2f;
        w = Mathf.Max(w, MinTouchSide);
        h = Mathf.Max(h, MinTouchSide);
        rt.sizeDelta = new Vector2(w, h);

        go.transform.SetSiblingIndex(targetRt.GetSiblingIndex() + 1);

        var img = go.AddComponent<Image>();
        var tex = Texture2D.whiteTexture;
        img.sprite = Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, 0.5f), 100f);
        img.color = new Color(1f, 1f, 1f, 0f);
        img.raycastTarget = true;

        var btn = go.AddComponent<Button>();
        btn.targetGraphic = img;
        btn.transition = Selectable.Transition.None;
        btn.onClick.AddListener(onClick);

        return btn;
    }
#endif
}
