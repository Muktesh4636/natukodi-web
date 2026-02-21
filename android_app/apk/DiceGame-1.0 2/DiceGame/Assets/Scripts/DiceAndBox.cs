using DG.Tweening;
using System;
using System.Collections.Generic;
using UnityEngine;

public class DiceAndBox : MonoBehaviour
{
    [Header("References")]
    public Camera diceCamera;
    public GameController gameController;
    public TargetedDiceRoller diceRoller;

    [Header("Dice Box")]
    public GameObject diceBox;
    public GameObject boxLid;
    public Animator boxAnimator;
    public Transform diceBoxTable;
    public Transform diceBoxShake;

    // --------- INTERNAL DATA ---------

    private int[] preDecidedResults;

    private Tween boxTween;

    private void Awake()
    {
        ResetDice();
    }

    // =========================================
    // STATE-SAFE PUBLIC API
    // =========================================

    public void RollSixDice()
    {
        int[] diceResults = new int[6]; // rolling 6 dice

        for (int i = 0; i < diceResults.Length; i++)
        {
            diceResults[i] = UnityEngine.Random.Range(1, 7); // generates numbers from 1 to 6
        }

        diceRoller.RollDices(diceResults);
    }

    public void SpawnDiceIfNeeded()
    {
        SpawnDice();
    }

    public void ShakeDiceIfNeeded()
    {
        if (diceBox == null) return;

        diceBox.SetActive(true);
        if (boxLid != null) boxLid.SetActive(true);

        AnimateDiceBox(
            diceBoxShake,
            0.5f,
            Ease.OutBack,
            () => boxAnimator.SetBool("Shake", true)
        );
    }


    public void ThrowDiceIfNeeded(int[] results)
    {
        if (results == null || results.Length == 0) return;

        preDecidedResults = results;

        boxAnimator.SetBool("Shake", false);
        boxAnimator.SetBool("ThrowDice", true);
        if (boxLid != null) boxLid.SetActive(false);

        // After animation, hide box (move back to table) and notify controller; do NOT spawn static dices here.
        // Static spawn should happen only when a player joins after dice result time (handled in GameController).
        Invoke(nameof(HideDiceBox), 1.5f);
    }

    public void ResetDice()
    {
        if (diceRoller != null)
            diceRoller.RemoveDices();

        SetBoxToTableImmediate();
    }

    public void SpawnDices(int[] results)
    {
        if (diceRoller == null) return;
        diceRoller.SpawnDices(results);
    }

    public void SetBoxToTableImmediate()
    {
        if (diceBox == null || diceBoxTable == null) return;

        boxTween?.Kill();

        diceBox.transform.SetPositionAndRotation(diceBoxTable.position, diceBoxTable.rotation);
        diceBox.transform.localScale = diceBoxTable.localScale;

        boxAnimator.SetBool("Shake", false);
        boxAnimator.SetBool("ThrowDice", false);
        if (boxLid != null) boxLid.SetActive(true);
        diceBox.SetActive(true);
    }

    // =========================================
    // INTERNAL LOGIC
    // =========================================

    private void SpawnDice()
    {
        if (preDecidedResults == null || preDecidedResults.Length == 0) return;
        if (diceRoller == null) return;

        // Use the roller to perform physics-based roll/playback
        diceRoller.RollDices(preDecidedResults);
    }

    private void HideDiceBox()
    {
        // Return box to table visually and stop any animator flags.
        boxAnimator.SetBool("ThrowDice", false);
        boxAnimator.SetBool("Shake", false);

        AnimateDiceBox(
            diceBoxTable,
            0.4f,
            Ease.InOutSine,
            () =>
            {
                if (boxLid != null) boxLid.SetActive(true);
            }
        );
        if (gameController != null)
            gameController.UpdateResult();
    }

    private void AnimateDiceBox(Transform target, float duration, Ease ease, Action onComplete = null)
    {
        boxTween?.Kill();

        boxTween = DOTween.Sequence()
            .Join(diceBox.transform.DOMove(target.position, duration).SetEase(ease))
            .Join(diceBox.transform.DORotateQuaternion(target.rotation, duration).SetEase(ease))
            .Join(diceBox.transform.DOScale(target.localScale, duration).SetEase(ease))
            .OnComplete(() => onComplete?.Invoke());
    }

}