using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

/// <summary>
/// Exports the Unity project for Android (Gradle/unityLibrary) via command line.
/// Run: Unity -batchmode -quit -projectPath "path" -executeMethod AndroidExportBuild.ExportAndroidProject
/// </summary>
public static class AndroidExportBuild
{
    private const string DefaultOutputFolder = "unityExport";

    /// <summary>
    /// Exports the Android project. Called from Unity Editor menu or -executeMethod.
    /// </summary>
    public static void ExportAndroidProject()
    {
        ExportAndroidProject(DefaultOutputFolder);
    }

    /// <summary>
    /// Exports the Android project to the given folder.
    /// </summary>
    public static void ExportAndroidProject(string outputFolder)
    {
        // Use output from command line if provided
        string[] args = System.Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
        {
            if (args[i] == "-exportPath" && !string.IsNullOrEmpty(args[i + 1]))
            {
                outputFolder = args[i + 1];
                break;
            }
        }

        string projectPath = System.IO.Path.GetDirectoryName(Application.dataPath);
        string fullOutputPath = System.IO.Path.IsPathRooted(outputFolder)
            ? outputFolder
            : System.IO.Path.Combine(projectPath, outputFolder);

        Debug.Log($"[AndroidExport] Exporting to: {fullOutputPath}");

        // Get scenes - use EditorBuildSettings or fallback to main game scenes
        string[] scenes = GetScenesForBuild();
        if (scenes == null || scenes.Length == 0)
        {
            Debug.LogError("[AndroidExport] No scenes found. Add scenes in File > Build Settings.");
            EditorApplication.Exit(1);
            return;
        }

        // Enable Export Project (Gradle/Android Studio)
        EditorUserBuildSettings.exportAsGoogleAndroidProject = true;

        // Switch to Android if not already
        if (EditorUserBuildSettings.activeBuildTarget != BuildTarget.Android)
        {
            Debug.Log("[AndroidExport] Switching to Android build target...");
            EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.Android, BuildTarget.Android);
        }

        var buildPlayerOptions = new BuildPlayerOptions
        {
            scenes = scenes,
            locationPathName = fullOutputPath,
            target = BuildTarget.Android,
            options = BuildOptions.None
        };

        BuildReport report = BuildPipeline.BuildPlayer(buildPlayerOptions);
        BuildSummary summary = report.summary;

        if (summary.result == BuildResult.Succeeded)
        {
            Debug.Log($"[AndroidExport] Export succeeded. Output: {fullOutputPath}");
            EditorApplication.Exit(0);
        }
        else
        {
            Debug.LogError($"[AndroidExport] Export failed: {summary.result}");
            EditorApplication.Exit(1);
        }
    }

    private static string[] GetScenesForBuild()
    {
        var editorScenes = EditorBuildSettings.scenes;
        if (editorScenes != null && editorScenes.Length > 0)
        {
            var list = new System.Collections.Generic.List<string>();
            foreach (var s in editorScenes)
            {
                if (s.enabled && !string.IsNullOrEmpty(s.path))
                    list.Add(s.path);
            }
            if (list.Count > 0)
                return list.ToArray();
        }

        // Fallback: main game scenes
        return new[] { "Assets/Scenes/MainGame.unity", "Assets/Scenes/Dice.unity" };
    }
}
