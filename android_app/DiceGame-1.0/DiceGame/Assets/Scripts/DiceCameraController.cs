using UnityEngine;
using DG.Tweening;

public enum DiceCameraState
{
    BettingView,
    DiceView
}

public class DiceCameraController : MonoBehaviour
{
    public GameObject characterImage;

    [Header("Camera")]
    public Camera diceCamera;

    [Header("Views")]
    public Transform bettingView;
    public float bettingFOV = 60f;

    public Transform diceView;
    public float diceFOV = 85f;

    [Header("Animation")]
    public float moveDuration = 0.6f;
    public Ease moveEase = Ease.InOutSine;

    private DiceCameraState currentState = DiceCameraState.BettingView;

    Tween camTween;
    Tween characterTween;

    public void MoveCamera(DiceCameraState state, bool animateCam)
    {
        if (currentState == state)
            return;

        currentState = state;

        Transform target;
        float targetFOV;
        float targetCharacterY;

        if (state == DiceCameraState.BettingView)
        {
            target = bettingView;
            targetFOV = bettingFOV;
            targetCharacterY = 0.45f;
        }
        else
        {
            target = diceView;
            targetFOV = diceFOV;
            targetCharacterY = 0.35f;
        }

        camTween?.Kill();
        characterTween?.Kill();

        Vector3 charPos = characterImage.transform.position;

        if (animateCam)
        {
            camTween = DOTween.Sequence()
                .Join(diceCamera.transform.DOMove(target.position, moveDuration).SetEase(moveEase))
                .Join(diceCamera.transform.DORotateQuaternion(target.rotation, moveDuration).SetEase(moveEase))
                .Join(diceCamera.DOFieldOfView(targetFOV, moveDuration).SetEase(moveEase));

            characterTween = characterImage.transform
                .DOMoveY(targetCharacterY, moveDuration)
                .SetEase(moveEase);
        }
        else
        {
            diceCamera.transform.SetPositionAndRotation(target.position, target.rotation);
            diceCamera.fieldOfView = targetFOV;

            characterImage.transform.position =
                new Vector3(charPos.x, targetCharacterY, charPos.z);
        }
    }
}