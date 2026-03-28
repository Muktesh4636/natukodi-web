using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using Random = UnityEngine.Random;

public class TargetedDiceRoller : MonoBehaviour
{
    public List<Transform> dicePoints;

    [Header("The thing we're gonna toss out.")]
    public TargetedDie DiePrefab;

    [Header("Slow Motion")]
    public bool UseSlowMotion = true;
    public float SlowMotionFactor = 20f;

    [Header("Keep this well within box bounds!!")]
    public Transform LaunchFrom;
    public Transform LaunchTarget;

    // Event invoked when physics playback completes and final numbers are available.
    public event Action<int[]> OnPlaybackComplete;

    const int NumFaces = 6;
    const int MaximumDieCount = 20;
    const int MaxSimulatorRetries = 15;
    const float UpperRollTimeLimit = 5.0f;

    List<TargetedDie> InstantiatedDice;
    List<int> NumbersQueued;
    Transform diceInFlightParent;
    List<Transform> usedDicePoints;

    float originalTimeScale;
    float originalFixedDeltaTime;

    bool queuedRoll;

    private void Awake()
    {
        NumbersQueued = new List<int> { 1, 2, 3, 4, 5, 6 };
        usedDicePoints = new List<Transform>();

        originalTimeScale = Time.timeScale;
        originalFixedDeltaTime = Time.fixedDeltaTime;
    }

    private void Start()
    {
        Physics.gravity = new Vector3(0, -200, 0);
    }

    void EnableSlowMotion()
    {
        if (!UseSlowMotion) return;

        Time.timeScale = originalTimeScale / SlowMotionFactor;
        Time.fixedDeltaTime = originalFixedDeltaTime / SlowMotionFactor;
    }

    void DisableSlowMotion()
    {
        Time.timeScale = originalTimeScale;
        Time.fixedDeltaTime = originalFixedDeltaTime;
    }

    void Update()
    {
        if (!queuedRoll) return;

        queuedRoll = false;

        EnableSlowMotion();

        if(diceInFlightParent != null)
            DestroyImmediate(diceInFlightParent.gameObject);

        bool good = false;
        int numRetries = MaxSimulatorRetries;

        while (numRetries-- > 0)
        {
            InstantiatedDice = new List<TargetedDie>();
            diceInFlightParent = new GameObject("diceInFlightParent").transform;

            float dieSpacing = 0f;

            int count = NumbersQueued.Count;
            int across = 1 + (int)Mathf.Sqrt(count * 2);
            int down = 1 + count / across;

            int index = 0;

            // Shuffle to avoid spatial bias
            var shuffled = new List<int>(NumbersQueued);
            for (int i = 0; i < shuffled.Count; i++)
            {
                int j = Random.Range(i, shuffled.Count);
                (shuffled[i], shuffled[j]) = (shuffled[j], shuffled[i]);
            }

            foreach (int number in shuffled)
            {
                int gridX = index % across;
                int gridY = index / across;

                Vector3 launchPos = LaunchFrom.position;
                launchPos.x += gridX * dieSpacing - across * dieSpacing * 0.5f;
                launchPos.y += gridY * dieSpacing - down * dieSpacing * 0.5f;
                launchPos.z += Random.Range(-dieSpacing, dieSpacing);

                TargetedDie die = Instantiate(
                    DiePrefab,
                    launchPos,
                    Random.rotation,
                    diceInFlightParent
                );

                int actualNumber = number == 0
                    ? Random.Range(1, NumFaces + 1)
                    : number;

                die.SetTargetNumber(actualNumber);
                InstantiatedDice.Add(die);

                index++;
            }

            foreach (TargetedDie die in InstantiatedDice)
            {
                Rigidbody rb = die.gameObject.AddComponent<Rigidbody>();

                rb.mass = 1.0f;
                rb.linearDamping = 0.2f;
                rb.angularDamping = 0.05f;
                rb.maxAngularVelocity = 750;
                rb.collisionDetectionMode = CollisionDetectionMode.ContinuousDynamic;

                Vector3 direction =
                    (LaunchTarget.position - die.transform.position).normalized;

                rb.linearVelocity = direction * Random.Range(15f, 25f);
                rb.angularVelocity = Random.onUnitSphere * Random.Range(20f, 30f);

                Vector3 torqueAxis = Random.onUnitSphere;
                float torqueStrength = Random.Range(40f, 60f);

                rb.AddTorque(torqueAxis * torqueStrength, ForceMode.Impulse);

                die.Go();
            }

            var holdSimulationMode = Physics.simulationMode;
            Physics.simulationMode = SimulationMode.Script;

            float stepTime = Time.fixedDeltaTime;

            for (float t = 0; t < UpperRollTimeLimit; t += stepTime)
            {
                bool anyMoving = false;

                foreach (TargetedDie die in InstantiatedDice)
                {
                    if (die.Record())
                        anyMoving = true;
                }

                if (!anyMoving)
                    break;

                Physics.Simulate(stepTime);
            }

            Physics.simulationMode = holdSimulationMode;

            int foulCount = 0;
            foreach (TargetedDie die in InstantiatedDice)
            {
                if (die.BeginPlayback())
                    foulCount++;
            }

            if(foulCount == 0 && !IsDiceStacked())
            {
                good = true;
                break;
            }

            DestroyImmediate(diceInFlightParent.gameObject);
        }

        if (good)
        {
            StartCoroutine(Playback());
        }
        else
        {
            DisableSlowMotion();
        }
    }

    public void RollDices(int[] results)
    {
        NumbersQueued = new List<int>(results);
        queuedRoll = true;
    }

    public void SpawnDices(int[] results)
    {
        if (results == null || results.Length == 0)
            return;

        int spawnCount = Mathf.Min(results.Length, dicePoints.Count);

        diceInFlightParent = new GameObject("diceInFlightParent").transform;

        usedDicePoints.Clear();

        List<Transform> availablePoints = new List<Transform>(dicePoints);

        for (int i = 0; i < spawnCount; i++)
        {
            int randomIndex = Random.Range(0, availablePoints.Count);
            Transform point = availablePoints[randomIndex];
            availablePoints.RemoveAt(randomIndex);

            TargetedDie die = Instantiate(
                DiePrefab,
                point.position,
                Quaternion.Euler(0f, Random.Range(0f, 360f), 0f),
                diceInFlightParent
            );

            die.SetTargetNumber(results[i]);
        }
    }

    /// <summary>Apply lightning effect to dice whose face value appears more than 2 times. Call after dice have settled and frequency is known.</summary>
    /// <param name="numbersWithHighFrequency">Set of dice values (1-6) that have frequency > 2.</param>
    public void ApplyLightningForNumbers(HashSet<int> numbersWithHighFrequency)
    {
        if (numbersWithHighFrequency == null) return;
        if (InstantiatedDice != null && InstantiatedDice.Count > 0)
        {
            foreach (TargetedDie die in InstantiatedDice)
                die.SetLightningEnabled(numbersWithHighFrequency.Contains(die.targetNumber));
            return;
        }
        if (diceInFlightParent != null)
        {
            foreach (TargetedDie die in diceInFlightParent.GetComponentsInChildren<TargetedDie>())
                die.SetLightningEnabled(numbersWithHighFrequency.Contains(die.targetNumber));
        }
    }

    private Quaternion GetPipRotation(int value)
    {
        switch (value)
        {
            case 1: return Quaternion.Euler(0, 0, 0);
            case 2: return Quaternion.Euler(90, 0, 0);
            case 3: return Quaternion.Euler(0, 0, 90);
            case 4: return Quaternion.Euler(0, 0, -90);
            case 5: return Quaternion.Euler(-90, 0, 0);
            case 6: return Quaternion.Euler(180, 0, 0);
            default:
                Debug.LogWarning($"Invalid dice value: {value}");
                return Quaternion.identity;
        }
    }


    bool IsDiceStacked()
    {
        for (int i = 0; i < InstantiatedDice.Count; i++)
        {
            Vector3 pos = InstantiatedDice[i].LastPosition();
            if (pos.y > 0.15f)
            {
                return true;
            }
        }

        return false;
    }

    IEnumerator Playback()
    {
        while (true)
        {
            bool anyMoving = false;

            foreach (TargetedDie die in InstantiatedDice)
            {
                if (die.PlaybackOneFrame())
                    anyMoving = true;
            }

            if (!anyMoving)
                break;

            yield return new WaitForSeconds(Time.fixedDeltaTime);
        }

        DisableSlowMotion();

        string finalResult = "";
        foreach (TargetedDie die in InstantiatedDice)
        {
            if (finalResult.Length > 0)
                finalResult += ", ";
            finalResult += die.targetNumber;
        }

        // build int[] and notify listeners that dice playback finished and final numbers are available
        try
        {
            int count = InstantiatedDice.Count;
            int[] finalNumbers = new int[count];
            for (int i = 0; i < count; i++)
                finalNumbers[i] = InstantiatedDice[i].targetNumber;

            OnPlaybackComplete?.Invoke(finalNumbers);
        }
        catch (Exception ex)
        {
            Debug.LogWarning("OnPlaybackComplete invoke failed: " + ex.Message);
        }

        // leave physics dice in scene so visuals remain; caller decides whether to spawn static dice later
    }

    public void RemoveDices()
    {
        if (diceInFlightParent != null)
        {
            Destroy(diceInFlightParent.gameObject);
            usedDicePoints.Clear();
        }
    }

    public bool IsDiceAlreadySpawned()
    {
        return diceInFlightParent != null;
    }
}