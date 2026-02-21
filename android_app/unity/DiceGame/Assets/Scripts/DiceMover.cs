using UnityEngine;

public class DiceMover : MonoBehaviour
{
    [Header("Movement Settings")]
    public float minTravelTime = 1.1f;
    public float maxTravelTime = 1.4f;
    public float minRotationSpeed = 360f;
    public float maxRotationSpeed = 720f;
    public float settleRotationSpeed = 6f;

    [Header("Rotation Phases")]
    public float spinPhaseEnd = 0.7f; // Stop wild spinning at 70% of travel
    public float settlePhaseStart = 0.85f; // Start settling at 85% of travel

    [Header("Scale Settings")]
    public float startScale = 0.07f;
    public float endScale = 0.125f;

    private Vector3[] points = new Vector3[6];
    private float travelTime;
    private Vector3 rotationAxis;
    private float rotationSpeed;
    private Quaternion startRotation;
    private Quaternion finalRotation;
    private int finalResult;
    private float t = 0f;
    private bool reached = false;
    private Camera diceCam;

    public void Initialize(Vector3 start, Vector3 end, float arcHeight, int result, Camera diceCam)
    {
        this.diceCam = diceCam;

        finalResult = result;
        finalRotation = GetDesiredRotation(finalResult);

        // Store starting rotation
        startRotation = transform.rotation;

        travelTime = Random.Range(minTravelTime, maxTravelTime);
        rotationSpeed = Random.Range(minRotationSpeed, maxRotationSpeed);

        // Random rotation axis for natural tumbling
        rotationAxis = Random.onUnitSphere;

        transform.localScale = Vector3.one * startScale;

        // P0 = Start
        points[0] = start;
        // P1 = upward boost + random
        points[1] = start + Vector3.up * arcHeight * 0.6f + Random.insideUnitSphere * 0.2f;
        // P2 = mid high arc turbulence
        points[2] = Vector3.Lerp(start, end, 0.33f) + Vector3.up * arcHeight + Random.insideUnitSphere * 0.3f;
        // P3 = descending turbulence
        points[3] = Vector3.Lerp(start, end, 0.66f) + Vector3.up * arcHeight * 0.6f + Random.insideUnitSphere * 0.3f;
        // P4 = near end, low wobble
        points[4] = end + Vector3.up * arcHeight * 0.2f + Random.insideUnitSphere * 0.1f;
        // P5 = End
        points[5] = end;
    }

    private void Update()
    {
        if (!reached)
        {
            t += Time.deltaTime / travelTime;
            float clampedT = Mathf.Clamp01(t);

            // Update position
            Vector3 pos = QuinticBezier(clampedT);
            transform.position = pos;

            // Update rotation with three phases
            UpdateRotation(clampedT);

            // Scale up during travel
            float scale = Mathf.Lerp(startScale, endScale, clampedT);
            transform.localScale = new Vector3(scale, scale, scale);

            if (clampedT >= 1f)
                reached = true;
        }
        else
        {
            // Final settle - smooth approach to exact result
            transform.rotation = Quaternion.Slerp(transform.rotation, finalRotation, Time.deltaTime * settleRotationSpeed);
        }
    }

    private void UpdateRotation(float t)
    {
        if (t < spinPhaseEnd)
        {
            // Phase 1: Wild tumbling (0% - 70%)
            float spinT = t / spinPhaseEnd;
            float currentSpeed = Mathf.Lerp(rotationSpeed, rotationSpeed * 0.5f, spinT);

            // Tumble around random axis
            transform.Rotate(rotationAxis, currentSpeed * Time.deltaTime, Space.World);
        }
        else if (t < settlePhaseStart)
        {
            // Phase 2: Transition phase (70% - 85%)
            // Gradually slow down and start orienting toward final rotation
            float transitionT = (t - spinPhaseEnd) / (settlePhaseStart - spinPhaseEnd);
            float slowedSpeed = rotationSpeed * 0.5f * (1f - transitionT);

            // Continue tumbling but slower
            transform.Rotate(rotationAxis, slowedSpeed * Time.deltaTime, Space.World);

            // Start blending toward final rotation
            float blendAmount = Mathf.SmoothStep(0f, 0.3f, transitionT);
            transform.rotation = Quaternion.Slerp(transform.rotation, finalRotation, blendAmount * Time.deltaTime * 2f);
        }
        else
        {
            // Phase 3: Settling phase (85% - 100%)
            // Smoothly rotate to final result
            float settleT = (t - settlePhaseStart) / (1f - settlePhaseStart);
            float settleStrength = Mathf.SmoothStep(0.3f, 1f, settleT);

            transform.rotation = Quaternion.Slerp(transform.rotation, finalRotation, settleStrength * Time.deltaTime * settleRotationSpeed);
        }
    }

    // 6-point Bezier (5th degree)
    private Vector3 QuinticBezier(float t)
    {
        float u = 1f - t;
        return
            Mathf.Pow(u, 5) * points[0] +
            5 * Mathf.Pow(u, 4) * t * points[1] +
            10 * Mathf.Pow(u, 3) * Mathf.Pow(t, 2) * points[2] +
            10 * Mathf.Pow(u, 2) * Mathf.Pow(t, 3) * points[3] +
            5 * u * Mathf.Pow(t, 4) * points[4] +
            Mathf.Pow(t, 5) * points[5];
    }

    private Quaternion GetDesiredRotation(int value)
    {
        int[] yOptions = { 0, 90, 180, 270 };
        int y = yOptions[Random.Range(0, yOptions.Length)];
        switch (value)
        {
            case 5: return Quaternion.Euler(0, y, 0);
            case 6: return Quaternion.Euler(90, y, 0);
            case 2: return Quaternion.Euler(180, y, 0);
            case 1: return Quaternion.Euler(270, y, 0);
            case 3: return Quaternion.Euler(0, y, 270);
            case 4: return Quaternion.Euler(0, y, 90);
            default: return Quaternion.identity;
        }
    }
}