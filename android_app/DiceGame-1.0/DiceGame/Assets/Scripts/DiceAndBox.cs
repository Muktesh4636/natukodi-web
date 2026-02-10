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

    [Header("Character")]
    public GameObject characterImage;

    // --------- INTERNAL DATA ---------

    private int[] preDecidedResults;

    private Tween boxTween;
    
    // Character Animation Data
    private Transform characterTransform;
    private Vector3 characterOriginalPos;
    private Tween characterTween;

    private void Awake()
    {
        ResetDice();
        
        // Initialize character reference
        if (characterImage != null)
        {
            characterTransform = characterImage.transform;
            characterOriginalPos = characterTransform.localPosition;
            Debug.Log("Character reference initialized successfully");
        }
        else
        {
            Debug.LogWarning("Character Image not assigned in Inspector!");
        }
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
        diceBox.SetActive(true);
        boxLid.SetActive(true);

        // Start Character Shake
        if (characterTransform != null)
        {
            Debug.Log("Starting Character Shake");
            characterTween?.Kill();
            characterTransform.localPosition = characterOriginalPos;
            characterTransform.localRotation = Quaternion.identity; // Reset rotation
            characterTransform.localScale = Vector3.one * 0.04f; // Reset scale (approximate, based on prefab)

            // Sequence for complex shake
            Sequence charSeq = DOTween.Sequence();
            
            // 1. Position Shake (Y-axis bob) - increased for visibility
            charSeq.Join(characterTransform.DOShakePosition(0.4f, new Vector3(0.02f, 0.05f, 0), 12, 80, false, true));
            
            // 2. Rotation Shake (Tilt) - increased for more visible "effort" effect
            charSeq.Join(characterTransform.DOShakeRotation(0.4f, new Vector3(5, 0, 25), 12, 80));
            
            // 3. Scale Punch (Squash/Stretch) - increased for visible "strain" effect
            charSeq.Join(characterTransform.DOPunchScale(new Vector3(0.015f, -0.01f, 0), 0.4f, 3, 0.5f));

            charSeq.SetLoops(-1, LoopType.Restart); // Loop the whole sequence
            characterTween = charSeq;
        }
        else
        {
            Debug.LogWarning("Character_Girl not found for shake animation");
        }

        AnimateDiceBox(
            diceBoxShake,
            0.5f,
            Ease.OutBack,
            () => boxAnimator.SetBool("Shake", true)
        );
    }


    public void ThrowDiceIfNeeded(int[] results)
    {
        preDecidedResults = results;

        // Stop Character Shake
        if (characterTransform != null)
        {
            Debug.Log("Stopping Character Shake");
            characterTween?.Kill();
            characterTransform.DOLocalMove(characterOriginalPos, 0.2f);
            characterTransform.DOLocalRotate(Vector3.zero, 0.2f);
            // characterTransform.DOScale(Vector3.one * 0.04f, 0.2f); // Optional reset if scale gets wonky
        }

        boxAnimator.SetBool("Shake", false);
        boxAnimator.SetBool("ThrowDice", true);
        boxLid.SetActive(false);

        // Notify WebGL bridge about dice roll start
        #if UNITY_WEBGL && !UNITY_EDITOR
        WebGLBridge.SendGameState("rolling");
        #endif

        Invoke(nameof(HideDiceBox), 1.5f);
    }

    public void ResetDice()
    {
        diceRoller.RemoveDices();
    }

    public void SpawnDices()
    {

    }
    // =========================================
    // INTERNAL LOGIC
    // =========================================

    private void SpawnDice()
    {
        diceRoller.RollDices(preDecidedResults);
    }

    private void HideDiceBox()
    {
        boxAnimator.SetBool("ThrowDice", false);
        boxAnimator.SetBool("Shake", false);
        
        // Ensure character is reset (redundant safety)
        if (characterTransform != null)
        {
            characterTween?.Kill();
            characterTransform.localPosition = characterOriginalPos;
        }

        AnimateDiceBox(
            diceBoxTable,
            0.4f,
            Ease.InOutSine,
            () =>
            {
                boxLid.SetActive(true);
                gameController.UpdateResult();

                // Notify WebGL bridge about dice roll completion
                #if UNITY_WEBGL && !UNITY_EDITOR
                WebGLBridge.SendDiceResults(preDecidedResults);
                WebGLBridge.SendGameState("completed");
                #endif
            }
        );
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