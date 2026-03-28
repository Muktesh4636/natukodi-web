using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class LoadingUIManager : MonoBehaviour
{
    public Slider loadingSlider;
    public TextMeshProUGUI loadingStatusText;

    private float loadingTime = 0;

    private void Start()
    {
        loadingSlider.value = 0;
        loadingStatusText.text = "Loading...";
        loadingTime = GameManager.Instance.loadingTime;
    }

    public void StartLoading()
    {
        AudioManager.Instance?.SetMuted(true);
        loadingSlider.value = 0;
        loadingStatusText.text = "Loading...";
        StartCoroutine(LoadingCoroutine());
    }

    private IEnumerator LoadingCoroutine()
    {
        float elapsed = 0f;

        while (elapsed < loadingTime)
        {
            // If no internet, pause progress and show waiting message
            if (Application.internetReachability == NetworkReachability.NotReachable)
            {
                loadingSlider.value = 0f;
                loadingStatusText.text = "Waiting for connection.....0%";

                // Poll for connection every 0.5s without advancing elapsed
                while (Application.internetReachability == NetworkReachability.NotReachable)
                {
                    yield return new WaitForSecondsRealtime(0.5f);
                }

                SceneManager.LoadSceneAsync(SceneManager.GetActiveScene().buildIndex);
                // When connection returns resume loop (do not reset elapsed)
            }

            elapsed += Time.deltaTime;

            float progress = Mathf.Clamp01(elapsed / loadingTime);
            UpdateLoadingProgress(progress);

            if (progress >= 0 && progress <= 0.45f) loadingStatusText.text = "Loading assets...";
            else if (progress >= 0.45f && progress <= 0.85f) loadingStatusText.text = "Setting up profile...";
            else if (progress >= 0.85f && progress <= 1f) loadingStatusText.text = "Almost there...";

            loadingStatusText.text += $" {Mathf.RoundToInt(progress * 100)}%";

            yield return null;
        }

        UpdateLoadingProgress(1f);
    }

    private void UpdateLoadingProgress(float progress)
    {
        loadingSlider.value = progress;

        if (progress >= 1f)
        {
            AudioManager.Instance?.SetMuted(false);
            UIManager.Instance.ShowPanel(UIPanelType.Gameplay);
        }
    }
}
