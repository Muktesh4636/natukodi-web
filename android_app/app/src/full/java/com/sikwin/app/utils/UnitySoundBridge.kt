package com.sikwin.app.utils

import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.SoundPool
import android.util.Log
import com.sikwin.app.R

/**
 * Bridge class to allow Unity to trigger sounds from the Android/Kotlin side.
 * 
 * Usage from Unity (C#):
 * 
 * public void PlayAndroidSound(string soundName, bool isLongSound = false) {
 *     using (AndroidJavaClass bridge = new AndroidJavaClass("com.sikwin.app.utils.UnitySoundBridge")) {
 *         bridge.CallStatic("playSound", soundName, isLongSound);
 *     }
 * }
 */
object UnitySoundBridge {
    private var mediaPlayer: MediaPlayer? = null
    private var soundPool: SoundPool? = null
    private val soundMap = mutableMapOf<String, Int>()

    init {
        val audioAttributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_GAME)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()
        
        soundPool = SoundPool.Builder()
            .setMaxStreams(10)
            .setAudioAttributes(audioAttributes)
            .build()
    }

    /**
     * Plays a sound from the Android raw resources.
     * @param soundName The name of the sound file (without extension) in res/raw
     * @param isLongSound If true, uses MediaPlayer (better for music/loops). If false, uses SoundPool (better for SFX).
     */
    @JvmStatic
    fun playSound(soundName: String, isLongSound: Boolean = false) {
        val context = (Class.forName("com.unity3d.player.UnityPlayer")
            .getField("currentActivity")
            .get(null) as? android.app.Activity) ?: return
        
        // Try to find the resource ID by name dynamically
        val resId = context.resources.getIdentifier(soundName, "raw", context.packageName)

        if (resId != 0) {
            if (isLongSound) {
                playWithMediaPlayer(context, resId, soundName)
            } else {
                playWithSoundPool(context, resId, soundName)
            }
        } else {
            Log.w("UnitySoundBridge", "Sound not found in res/raw: $soundName")
        }
    }

    private fun playWithMediaPlayer(context: android.content.Context, resId: Int, soundName: String) {
        try {
            mediaPlayer?.stop()
            mediaPlayer?.release()
            
            mediaPlayer = MediaPlayer.create(context, resId)
            mediaPlayer?.setOnCompletionListener { 
                it.release() 
                if (mediaPlayer == it) mediaPlayer = null
            }
            mediaPlayer?.start()
            Log.d("UnitySoundBridge", "Playing long sound (MediaPlayer): $soundName")
        } catch (e: Exception) {
            Log.e("UnitySoundBridge", "Error playing MediaPlayer sound: $soundName", e)
        }
    }

    private fun playWithSoundPool(context: android.content.Context, resId: Int, soundName: String) {
        try {
            val soundId = if (soundMap.containsKey(soundName)) {
                soundMap[soundName]!!
            } else {
                val id = soundPool?.load(context, resId, 1) ?: 0
                soundMap[soundName] = id
                id
            }

            // SoundPool.load is async, so if it's the first time, we might need a small delay or listener
            // For simplicity in games, we just play it. If it's already loaded, it plays instantly.
            soundPool?.play(soundId, 1.0f, 1.0f, 1, 0, 1.0f)
            Log.d("UnitySoundBridge", "Playing short sound (SoundPool): $soundName")
        } catch (e: Exception) {
            Log.e("UnitySoundBridge", "Error playing SoundPool sound: $soundName", e)
        }
    }

    /**
     * Stops any currently playing long sounds.
     */
    @JvmStatic
    fun stopAllSounds() {
        try {
            mediaPlayer?.stop()
            mediaPlayer?.release()
            mediaPlayer = null
            
            // Note: SoundPool sounds are usually short and don't need manual stopping,
            // but you can call soundPool.autoPause() if needed.
            Log.d("UnitySoundBridge", "All long sounds stopped")
        } catch (e: Exception) {
            Log.e("UnitySoundBridge", "Error stopping sounds", e)
        }
    }
}
