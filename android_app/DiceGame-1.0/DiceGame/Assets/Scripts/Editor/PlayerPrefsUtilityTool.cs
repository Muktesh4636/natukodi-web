using UnityEditor;
using UnityEngine;

public class PlayerPrefsUtilityTool : EditorWindow
{
    private string keyToDelete = "";

    [MenuItem("Tools/PlayerPrefs Utility")]
    public static void OpenWindow()
    {
        GetWindow<PlayerPrefsUtilityTool>("PlayerPrefs Utility");
    }

    private void OnGUI()
    {
        GUILayout.Label("PlayerPrefs Utility Tool", EditorStyles.boldLabel);
        GUILayout.Space(10);

        DrawDeleteSingleKeySection();
        GUILayout.Space(15);
        DrawDeleteAllKeysSection();

        GUILayout.Space(20);
        DrawFutureToolsSection();
    }

    // ===============================
    // DELETE SINGLE KEY
    // ===============================
    private void DrawDeleteSingleKeySection()
    {
        GUILayout.Label("Delete Specific Key", EditorStyles.label);

        keyToDelete = EditorGUILayout.TextField("Key Name", keyToDelete);

        GUI.enabled = !string.IsNullOrEmpty(keyToDelete);
        if (GUILayout.Button("Delete Key"))
        {
            DeleteSingleKey(keyToDelete);
        }
        GUI.enabled = true;
    }

    private void DeleteSingleKey(string key)
    {
        if (!PlayerPrefs.HasKey(key))
        {
            EditorUtility.DisplayDialog(
                "Key Not Found",
                $"PlayerPrefs key \"{key}\" does not exist.",
                "OK"
            );
            return;
        }

        if (!EditorUtility.DisplayDialog(
                "Confirm Delete",
                $"Are you sure you want to delete PlayerPrefs key:\n\n{key}",
                "Delete",
                "Cancel"))
        {
            return;
        }

        PlayerPrefs.DeleteKey(key);
        PlayerPrefs.Save();

        Debug.Log($"Deleted PlayerPrefs key: {key}");
    }

    // ===============================
    // DELETE ALL KEYS
    // ===============================
    private void DrawDeleteAllKeysSection()
    {
        GUILayout.Label("Danger Zone", EditorStyles.boldLabel);

        GUI.color = Color.red;
        if (GUILayout.Button("Delete ALL PlayerPrefs"))
        {
            DeleteAllKeys();
        }
        GUI.color = Color.white;
    }

    private void DeleteAllKeys()
    {
        if (!EditorUtility.DisplayDialog(
                "Delete ALL PlayerPrefs",
                "This will permanently delete ALL PlayerPrefs keys.\n\nAre you sure?",
                "Delete All",
                "Cancel"))
        {
            return;
        }

        PlayerPrefs.DeleteAll();
        PlayerPrefs.Save();

        Debug.Log("All PlayerPrefs keys deleted.");
    }

    // ===============================
    // FUTURE EXTENSIONS
    // ===============================
    private void DrawFutureToolsSection()
    {
        GUILayout.Label("More Tools (Coming Soon)", EditorStyles.miniBoldLabel);

        EditorGUILayout.HelpBox(
            "Planned features:\n" +
            "• List all PlayerPrefs keys\n" +
            "• Export / Import PlayerPrefs\n" +
            "• Delete by prefix\n" +
            "• Environment-based PlayerPrefs\n" +
            "• Cloud Save sync helpers",
            MessageType.Info
        );
    }
}