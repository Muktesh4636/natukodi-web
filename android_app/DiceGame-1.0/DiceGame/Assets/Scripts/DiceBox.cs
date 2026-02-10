using UnityEngine;

public class DiceBox : MonoBehaviour
{
    public DiceAndBox diceAndBox;

    public void ThrowDices()
    {
        diceAndBox.SpawnDiceIfNeeded();
    }
}