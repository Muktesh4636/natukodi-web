using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using TMPro;

[RequireComponent(typeof(ScrollRect))]
public class MobileKeyboardScroller : MonoBehaviour
{
    [Header("Settings")]
    [Tooltip("Extra space between input field and keyboard (pixels)")]
    public float padding = 30f;

    [Tooltip("Scroll animation speed")]
    public float scrollSpeed = 10f;

    private ScrollRect scrollRect;
    private RectTransform content;
    private Canvas canvas;

    private Vector2 originalContentSize;
    private Vector2 targetPosition;
    private bool isScrolling;
    private int lastKeyboardHeight;

    void Awake()
    {
        scrollRect = GetComponent<ScrollRect>();
        content = scrollRect.content;
        canvas = GetComponentInParent<Canvas>();

        originalContentSize = content.sizeDelta;
    }

    void Update()
    {
#if UNITY_ANDROID || UNITY_IOS
        HandleKeyboard();
#endif
        SmoothScroll();
    }

    void HandleKeyboard()
    {
        int keyboardHeight = GetKeyboardHeight();

        if (keyboardHeight != lastKeyboardHeight)
        {
            lastKeyboardHeight = keyboardHeight;

            if (keyboardHeight > 0)
                ScrollToFocusedInput(keyboardHeight);
            else
                ResetScroll();
        }
    }

    int GetKeyboardHeight()
    {
        if (TouchScreenKeyboard.visible)
        {
            return (int)(Screen.height * TouchScreenKeyboard.area.height);
        }
        return 0;
    }

    void ScrollToFocusedInput(int keyboardHeight)
    {
        GameObject selected = EventSystem.current.currentSelectedGameObject;
        if (selected == null) return;

        RectTransform inputRect = selected.GetComponent<RectTransform>();
        if (inputRect == null) return;

        Vector3[] corners = new Vector3[4];
        inputRect.GetWorldCorners(corners);

        float inputBottomY = corners[0].y;
        float keyboardTopY = keyboardHeight;

        float scaleFactor = canvas.scaleFactor;
        float delta = (keyboardTopY + padding) - inputBottomY;

        if (delta <= 0) return;

        content.sizeDelta = originalContentSize + new Vector2(0, delta / scaleFactor);

        targetPosition = content.anchoredPosition + new Vector2(0, delta / scaleFactor);
        isScrolling = true;
    }

    void ResetScroll()
    {
        content.sizeDelta = originalContentSize;
        targetPosition = content.anchoredPosition;
        isScrolling = false;
    }

    void SmoothScroll()
    {
        if (!isScrolling) return;

        content.anchoredPosition = Vector2.Lerp(
            content.anchoredPosition,
            targetPosition,
            Time.deltaTime * scrollSpeed
        );
    }
}
