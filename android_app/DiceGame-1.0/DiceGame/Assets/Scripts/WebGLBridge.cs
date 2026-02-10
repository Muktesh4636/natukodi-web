using UnityEngine;
using System.Runtime.InteropServices;

public class WebGLBridge : MonoBehaviour
{
    [DllImport("__Internal")]
    private static extern void SendMessageToReact(string message);

    [DllImport("__Internal")]
    private static extern void OnDiceRollComplete(string results);

    [DllImport("__Internal")]
    private static extern void OnGameStateChanged(string state);

    // Singleton instance
    private static WebGLBridge instance;

    private void Awake()
    {
        if (instance == null)
        {
            instance = this;
            DontDestroyOnLoad(gameObject);
        }
        else
        {
            Destroy(gameObject);
        }
    }

    // Methods called by Unity code to communicate with React
    public static void SendDiceResults(int[] results)
    {
        string resultString = string.Join(",", results);
        OnDiceRollComplete(resultString);
    }

    public static void SendGameState(string state)
    {
        OnGameStateChanged(state);
    }

    public static void SendCustomMessage(string message)
    {
        SendMessageToReact(message);
    }

    // Methods called by JavaScript/React to control Unity
    public void RollDice(string diceValues)
    {
        // Parse the dice values from JavaScript
        string[] values = diceValues.Split(',');
        int[] results = new int[values.Length];

        for (int i = 0; i < values.Length; i++)
        {
            if (int.TryParse(values[i], out int result))
            {
                results[i] = result;
            }
        }

        // Find the dice controller and trigger roll
        DiceAndBox diceController = FindFirstObjectByType<DiceAndBox>();
        if (diceController != null)
        {
            diceController.ThrowDiceIfNeeded(results);
        }
    }

    public void StartShakeAnimation()
    {
        DiceAndBox diceController = FindFirstObjectByType<DiceAndBox>();
        if (diceController != null)
        {
            diceController.ShakeDiceIfNeeded();
        }
    }

    public void ResetDice()
    {
        DiceAndBox diceController = FindFirstObjectByType<DiceAndBox>();
        if (diceController != null)
        {
            diceController.ResetDice();
        }
    }

    public void UpdateGameState(string state)
    {
        GameController gameController = FindFirstObjectByType<GameController>();
        if (gameController != null)
        {
            // Handle state updates from React
            Debug.Log($"Game state updated to: {state}");
        }
    }
}