using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class TargetedDie : MonoBehaviour
{
    public Transform Pips;

    /// <summary>Optional: assign a child GameObject with particle system or glow for "hot" dice (frequency > 2).</summary>
    [Tooltip("Optional lightning/glow effect - enabled when this die's number appears more than 2 times.")]
    public GameObject lightningEffect;

    public int targetNumber { get; private set; }

    List<Vector3> positions;
    List<Quaternion> rotations;
    int playbackHead;

    Quaternion[] orientationsFaceUp
    {
        get
        {
            return new Quaternion[]
            {
                Quaternion.Euler(0,0,0),
                Quaternion.Euler(+90, 0, 0),
                Quaternion.Euler(0, 0, +90),
                Quaternion.Euler(0, 0, -90),
                Quaternion.Euler(-90, 0, 0),
                Quaternion.Euler(180, 0, 0),
            };
        }
    }

    Quaternion[] orientationsFaceDown
    {
        get
        {
            return new Quaternion[]
            {
                Quaternion.Euler(180, 0, 0),
                Quaternion.Euler(-90, 0, 0),
                Quaternion.Euler(0, 0, -90),
                Quaternion.Euler(0, 0, +90),
                Quaternion.Euler(+90, 0, 0),
                Quaternion.Euler(0,0,0),
            };
        }
    }

    Quaternion[] orientationsOnLeftSide
    {
        get
        {
            return new Quaternion[]
            {
                Quaternion.Euler(0,0,-90),
                Quaternion.Euler(0,-90,0),
                Quaternion.Euler(0,0,0),
                Quaternion.Euler(0,180,0),
                Quaternion.Euler(0,+90,0),
                Quaternion.Euler(0,0,+90),
            };
        }
    }

    Quaternion[] orientationsOnRightSide
    {
        get
        {
            return new Quaternion[]
            {
                Quaternion.Euler(0,0,+90),
                Quaternion.Euler(0,+90,0),
                Quaternion.Euler(0,180,0),
                Quaternion.Euler(0,0,0),
                Quaternion.Euler(0,-90,0),
                Quaternion.Euler(0,0,-90),
            };
        }
    }

    Quaternion[] orientationsTippedForward
    {
        get
        {
            return new Quaternion[]
            {
                Quaternion.Euler(-90,0,0),
                Quaternion.Euler(0,0,0),
                Quaternion.Euler(0,+90,0),
                Quaternion.Euler(0,-90,0),
                Quaternion.Euler(0,180,0),
                Quaternion.Euler(+90,0,0),
            };
        }
    }

    Quaternion[] orientationsTippedBackward
    {
        get
        {
            return new Quaternion[]
            {
                Quaternion.Euler(+90,0,0),
                Quaternion.Euler(0,180,0),
                Quaternion.Euler(0,-90,0),
                Quaternion.Euler(0,+90,0),
                Quaternion.Euler(0,0,0),
                Quaternion.Euler(-90,0,0),
            };
        }
    }

    int faceCount
    {
        get
        {
            return orientationsFaceUp.Length;
        }
    }

    // expects 1 to faceCount
    public void SetTargetNumber(int number)
    {
        if (number > 0 && number <= faceCount)
        {
            targetNumber = number;

            int numberIndex = number - 1;

            Pips.localRotation = orientationsFaceUp[numberIndex];

            return;
        }

        targetNumber = -1;
        throw new System.IndexOutOfRangeException(
            System.String.Format("This die only supports 1 to {0}", faceCount));
    }

    /// <summary>Show or hide lightning effect (e.g. when this die's number has frequency > 2).</summary>
    public void SetLightningEnabled(bool enabled)
    {
        if (lightningEffect != null)
            lightningEffect.SetActive(enabled);
    }

    Rigidbody rb;

    public void Go()
    {
        rb = GetComponent<Rigidbody>();

        positions = new List<Vector3>();
        rotations = new List<Quaternion>();
    }

    public bool Record()
    {
        positions.Add(transform.position);
        rotations.Add(transform.rotation);

        bool moving = false;

        if (rb)
        {
            if (rb.linearVelocity.magnitude > 1.0f)
            {
                moving = true;
            }
        }

        return moving;
    }

    public Vector3 LastPosition()
    {
        if(positions == null || positions.Count == 0)
            return transform.position;

        return positions[positions.Count - 1];
    }

    public Quaternion LastRotation()
    {
        if(rotations == null || rotations.Count == 0)
            return transform.rotation;
        return rotations[rotations.Count - 1];
    }

    // you may want to remove this if you're rolling on massively uneven surfaces...
    // if you do, you may wish to detect stacked final dice, such as being too near in a horizontal plane
    const float ExpectedFinalHeight = 1.0f;
    const float MaxHeightDeviance = 2.0f;

    // returns true if fouled, false if good
    public bool BeginPlayback()
    {
        if (rb)
        {
            DestroyImmediate(rb);
        }

        // detect dice stacked on each other; see notes above about uneven playing fields...
        var position = transform.position;
        if (Mathf.Abs(position.y - ExpectedFinalHeight) > MaxHeightDeviance)
        {
            return true;
        }

        // we have arrived so now we have to figure out our
        // orientation and then adjust the pips accordingly.

        // the larger this is the more chance of a fouled die
        // this number is the cosine of the most-tipped you want the die to end up
        // guide: 0.99f -> 8 degrees 
        const float threshold = 0.97f;

        int numberIndex = targetNumber - 1;

        Quaternion? finalRotation = null;

        Vector3 up = transform.up;

        // upright?
        if (up.y > +threshold)
        {
            // the top is by default mapped after we set our
            // rotation originally, so we're done
            finalRotation = orientationsFaceUp[numberIndex];
        }
        // inverted?
        if (up.y < -threshold)
        {
            finalRotation = orientationsFaceDown[numberIndex];
        }

        Vector3 right = transform.right;


        // on left side?
        if (right.y > +threshold)
        {
            finalRotation = orientationsOnLeftSide[numberIndex];
        }
        // on right side?
        if (right.y < -threshold)
        {
            finalRotation = orientationsOnRightSide[numberIndex];
        }

        Vector3 forward = transform.forward;


        // tipped forward?
        if (forward.y < -threshold)
        {
            finalRotation = orientationsTippedForward[numberIndex];
        }
        // tipped backward?
        if (forward.y > +threshold)
        {
            finalRotation = orientationsTippedBackward[numberIndex];
        }

        if (finalRotation == null)
        {
            return true;
        }

        Pips.localRotation = (Quaternion)finalRotation;

        playbackHead = 0;
        PlaybackOneFrame();
        playbackHead = 0;

        return false;
    }

    public bool PlaybackOneFrame()
    {
        if (playbackHead >= 0 && playbackHead < positions.Count)
        {
            transform.position = positions[playbackHead];
            transform.rotation = rotations[playbackHead];
        }

        playbackHead++;

        return playbackHead < positions.Count;
    }

    void Awake()
    {
        targetNumber = -1;
    }

    private void OnCollisionEnter(Collision collision)
    {
        if (rb)
        {
            rb.linearDamping += 0.15f;
            rb.angularDamping += 0.15f;
        }
    }
}
