using UnityEngine;
using UnityEditor;
using System.IO;

public class BuildScript
{
    [MenuItem("Build/Build WebGL")]
    public static void BuildWebGL()
    {
        string[] scenes = {
            "Assets/Scenes/MainGame.unity"
        };

        string buildPath = Path.Combine(Application.dataPath, "../Builds/WebGL");

        // Create build directory if it doesn't exist
        if (!Directory.Exists(buildPath))
        {
            Directory.CreateDirectory(buildPath);
        }

        BuildPlayerOptions buildPlayerOptions = new BuildPlayerOptions();
        buildPlayerOptions.scenes = scenes;
        buildPlayerOptions.locationPathName = Path.Combine(buildPath, "index.html");
        buildPlayerOptions.target = BuildTarget.WebGL;
        buildPlayerOptions.options = BuildOptions.None;

        // Set WebGL specific settings
        PlayerSettings.WebGL.linkerTarget = WebGLLinkerTarget.Asm;
        PlayerSettings.WebGL.threadsSupport = false;
        PlayerSettings.WebGL.memorySize = 256;
        PlayerSettings.WebGL.exceptionSupport = WebGLExceptionSupport.FullWithoutStacktrace;

        // Build the player
        BuildPipeline.BuildPlayer(buildPlayerOptions);

        Debug.Log("WebGL Build completed!");
    }

    [MenuItem("Build/Build WebGL Development")]
    public static void BuildWebGLDevelopment()
    {
        string[] scenes = {
            "Assets/Scenes/MainGame.unity"
        };

        string buildPath = Path.Combine(Application.dataPath, "../Builds/WebGL_Dev");

        if (!Directory.Exists(buildPath))
        {
            Directory.CreateDirectory(buildPath);
        }

        BuildPlayerOptions buildPlayerOptions = new BuildPlayerOptions();
        buildPlayerOptions.scenes = scenes;
        buildPlayerOptions.locationPathName = Path.Combine(buildPath, "index.html");
        buildPlayerOptions.target = BuildTarget.WebGL;
        buildPlayerOptions.options = BuildOptions.Development | BuildOptions.ConnectWithProfiler;

        PlayerSettings.WebGL.linkerTarget = WebGLLinkerTarget.Asm;
        PlayerSettings.WebGL.threadsSupport = false;
        PlayerSettings.WebGL.memorySize = 256;
        PlayerSettings.WebGL.exceptionSupport = WebGLExceptionSupport.FullWithoutStacktrace;

        BuildPipeline.BuildPlayer(buildPlayerOptions);

        Debug.Log("WebGL Development Build completed!");
    }
}