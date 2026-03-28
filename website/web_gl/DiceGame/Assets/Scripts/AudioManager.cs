using UnityEngine;

public enum SfxType
{
    CoinSfx,
    DiceRollSfx,
    PlaceBetSfx,
    CloseBetSfx,
    ShakingSfx
}

[RequireComponent(typeof(AudioSource))]
public class AudioManager : MonoBehaviour
{
    public static AudioManager Instance { get; private set; }

    [Header("SFX Clips")]
    public AudioClip coinSfx;
    public AudioClip diceRollSfx;
    public AudioClip placeBetSfx;
    public AudioClip closeBetSfx;
    public AudioClip shakingSfx;

    [Header("Background Music")]
    public AudioClip bgMusicClip;   // Assign music file in inspector
    [Range(0f, 1f)]
    public float backgroundMusicVolume = 0.5f;

    private AudioSource sfxSource;
    private AudioSource bgSource;

    private bool isMuted = false;

    public bool IsMuted => isMuted;

    private void Awake()
    {
        if (Instance == null)
        {
            Instance = this;
            DontDestroyOnLoad(gameObject);
        }
        else
        {
            Destroy(gameObject);
            return;
        }
    }

    private void Start()
    {
        // SFX source (already attached due to RequireComponent)
        sfxSource = GetComponent<AudioSource>();

        // Create dedicated background music source
        bgSource = gameObject.AddComponent<AudioSource>();
        bgSource.loop = true;
        bgSource.playOnAwake = false;
        bgSource.volume = backgroundMusicVolume;

        if (bgMusicClip != null)
        {
            bgSource.clip = bgMusicClip;
            bgSource.Play();
        }

        SetMuted(true);
    }

    // -------------------- SFX --------------------

    public void PlaySfx(SfxType sfxType, bool loop = false, float volume = 1f)
    {
        if (isMuted) return;

        AudioClip clip = GetClip(sfxType);
        if (clip == null) return;

        sfxSource.volume = volume;

        if (loop)
        {
            if (sfxSource.clip == clip && sfxSource.isPlaying) return;

            sfxSource.clip = clip;
            sfxSource.loop = true;
            sfxSource.Play();
        }
        else
        {
            sfxSource.loop = false;
            sfxSource.PlayOneShot(clip);
        }
    }

    public void StopSfx()
    {
        sfxSource.loop = false;
        sfxSource.Stop();
        sfxSource.clip = null;
    }

    private AudioClip GetClip(SfxType type)
    {
        switch (type)
        {
            case SfxType.CoinSfx: return coinSfx;
            case SfxType.DiceRollSfx: return diceRollSfx;
            case SfxType.PlaceBetSfx: return placeBetSfx;
            case SfxType.CloseBetSfx: return closeBetSfx;
            case SfxType.ShakingSfx: return shakingSfx;
        }
        return null;
    }

    // -------------------- Background Music --------------------

    public void PlayBackgroundMusic()
    {
        if (isMuted || bgSource == null || bgMusicClip == null) return;

        if (!bgSource.isPlaying)
            bgSource.Play();
    }

    public void PauseBackgroundMusic()
    {
        if (bgSource != null && bgSource.isPlaying)
            bgSource.Pause();
    }

    public void StopBackgroundMusic()
    {
        if (bgSource != null)
            bgSource.Stop();
    }

    public void SetBackgroundMusicVolume(float volume)
    {
        backgroundMusicVolume = Mathf.Clamp01(volume);
        if (bgSource != null)
            bgSource.volume = backgroundMusicVolume;
    }

    public void SetMuted(bool muted)
    {
        isMuted = muted;

        if (isMuted)
        {
            StopSfx();
            PauseBackgroundMusic();
        }
        else
        {
            PlayBackgroundMusic();
        }
    }
}
