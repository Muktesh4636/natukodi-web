using UnityEngine;

[ExecuteAlways]
public class SafeArea : MonoBehaviour
{
    private RectTransform panel;
    private Rect safeArea;
    private Canvas canvas;

    private void Awake()
    {
        panel = GetComponent<RectTransform>();
        canvas = GetComponentInParent<Canvas>();

        ApplySafeArea();
    }

    private void OnEnable()
    {
        ApplySafeArea();
    }

#if UNITY_EDITOR
    private void Update()
    {
        // Re-apply in editor when resolution changes
        ApplySafeArea();
    }
#endif

    void ApplySafeArea()
    {
        if (panel == null || canvas == null)
            return;

        Rect currentSafeArea = Screen.safeArea;

        if (currentSafeArea != safeArea)
        {
            safeArea = currentSafeArea;
            Apply();
        }
    }

    void Apply()
    {
        // Convert safe area rectangle from screen space → anchor space
        Vector2 anchorMin = safeArea.position;
        Vector2 anchorMax = safeArea.position + safeArea.size;

        anchorMin.x /= Screen.width;
        anchorMin.y /= Screen.height;
        anchorMax.x /= Screen.width;
        anchorMax.y /= Screen.height;

        panel.anchorMin = anchorMin;
        panel.anchorMax = anchorMax;
    }
}
