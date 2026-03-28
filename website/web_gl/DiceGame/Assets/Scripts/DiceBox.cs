using UnityEngine;

public class DiceBox : MonoBehaviour
{
    public DiceAndBox diceAndBox;

    public void ThrowDices()
    {
        diceAndBox.SpawnDiceIfNeeded();
        Invoke(nameof(PlayDiceRollSfx), 0.1f);
    }

    private void PlayDiceRollSfx()
    {
        AudioManager.Instance?.PlaySfx(SfxType.DiceRollSfx);
        try { AudioManager.Instance?.PlayBackgroundMusic(); } catch { }
    }
}