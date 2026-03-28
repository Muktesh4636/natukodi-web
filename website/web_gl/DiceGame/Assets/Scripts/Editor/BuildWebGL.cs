using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

/// <summary>
/// Call from command line: Unity -quit -batchmode -projectPath ... -executeMethod BuildWebGL.BuildFromCommandLine
/// </summary>
public static class BuildWebGL
{
    public static void BuildFromCommandLine()
    {
        if (EditorUserBuildSettings.activeBuildTarget != BuildTarget.WebGL)
        {
            EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.WebGL, BuildTarget.WebGL);
        }

        // Smaller IL2CPP output = less wasm to download (rebuild WebGL after changing this)
        PlayerSettings.SetManagedStrippingLevel(BuildTargetGroup.WebGL, ManagedStrippingLevel.High);
        EditorUserBuildSettings.development = false;

        string buildPath = "Builds/WebGL";
        BuildPlayerOptions opts = new BuildPlayerOptions
        {
            scenes = GetEnabledScenePaths(),
            locationPathName = buildPath,
            target = BuildTarget.WebGL,
            options = BuildOptions.None
        };
        var report = BuildPipeline.BuildPlayer(opts);
        if (report.summary.result != BuildResult.Succeeded)
        {
            throw new System.Exception("WebGL build failed: " + report.summary.result);
        }

        PatchIndexForParallelLoad(buildPath);
    }

    /// <summary>
    /// Unity regenerates index.html each build; inject link rel=preload so .data/.wasm/.framework fetch in parallel with the loader.
    /// </summary>
    static void PatchIndexForParallelLoad(string buildPath)
    {
        string indexPath = Path.Combine(buildPath, "index.html");
        if (!File.Exists(indexPath)) return;

        string html = File.ReadAllText(indexPath);
        if (html.Contains("rel=\"preload\"") && html.Contains("WebGL.loader")) return;

        string buildDir = Path.Combine(buildPath, "Build");
        string ext = File.Exists(Path.Combine(buildDir, "WebGL.data.br")) ? ".br"
            : File.Exists(Path.Combine(buildDir, "WebGL.data.gz")) ? ".gz"
            : null;
        if (ext == null) return;

        string inject = $@"    <link rel=""preload"" href=""Build/WebGL.loader.js"" as=""script"" fetchpriority=""high"">
    <link rel=""preload"" href=""Build/WebGL.data{ext}"" as=""fetch"" crossorigin=""anonymous"">
    <link rel=""preload"" href=""Build/WebGL.framework.js{ext}"" as=""fetch"" crossorigin=""anonymous"">
    <link rel=""preload"" href=""Build/WebGL.wasm{ext}"" as=""fetch"" crossorigin=""anonymous"">
";

        int headOpen = html.IndexOf("<head>", System.StringComparison.OrdinalIgnoreCase);
        if (headOpen < 0) return;
        int insertAt = html.IndexOf('>', headOpen) + 1;
        html = html.Insert(insertAt, "\n" + inject);

        html = html.Replace(
            "<link rel=\"stylesheet\" href=\"TemplateData/style.css\">",
            "<link rel=\"stylesheet\" href=\"TemplateData/style.css\" media=\"print\" onload=\"this.media='all'\">\n    <noscript><link rel=\"stylesheet\" href=\"TemplateData/style.css\"></noscript>");

        File.WriteAllText(indexPath, html);
    }

    static string[] GetEnabledScenePaths()
    {
        var scenes = new System.Collections.Generic.List<string>();
        foreach (var s in EditorBuildSettings.scenes)
        {
            if (s.enabled && !string.IsNullOrEmpty(s.path))
                scenes.Add(s.path);
        }
        return scenes.ToArray();
    }
}
