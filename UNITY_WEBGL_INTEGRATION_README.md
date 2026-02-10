# Unity WebGL Integration for Dice Game

This guide explains how to build and integrate your Unity dice game into a web browser using WebGL.

## Overview

Your Unity project (`DiceGame-1.0`) has been enhanced with WebGL support and React integration. The Unity game will run directly in the browser and communicate with your React frontend.

## Files Added/Modified

### Unity Project Changes
- `Assets/Editor/BuildScript.cs` - Build automation script
- `Assets/Scripts/WebGLBridge.cs` - Communication layer between Unity and JavaScript
- `Assets/Scripts/DiceAndBox.cs` - Updated to notify WebGL about dice roll completion

### Web Integration Files
- `web_dice_game_component.tsx` - React component for Unity WebGL integration
- `DiceGamePage.tsx` - Sample page showing how to use the Unity component
- `web_build_template.html` - Template for Unity WebGL build
- `build_webgl.sh` - Build script for WebGL

## Step-by-Step Setup

### 1. Open Unity Project

Open the Unity project in Unity Editor:
```
android_app/DiceGame-1.0/DiceGame
```

### 2. Configure WebGL Build Settings

1. In Unity Editor: **File > Build Settings**
2. Select **WebGL** as the target platform
3. Click **Switch Platform**
4. In **Player Settings**:
   - Set **WebGL Memory Size** to 256 MB
   - Disable **Threads Support** (for broader browser compatibility)
   - Set **Exception Support** to "Full Without Stacktrace"

### 3. Build for WebGL

#### Option A: Using Unity Editor
1. **File > Build Settings**
2. Ensure `Assets/Scenes/MainGame.unity` is in the Scenes list
3. Click **Build** and select output folder: `Builds/WebGL`

#### Option B: Using Build Script
Run the provided build script:
```bash
chmod +x build_webgl.sh
./build_webgl.sh
```

**Note:** Update the `UNITY_EXECUTABLE` path in `build_webgl.sh` to match your Unity installation.

### 4. Deploy Build Files

Copy the built WebGL files to your backend static folder:
```bash
mkdir -p backend/static/unity
cp -r android_app/DiceGame-1.0/DiceGame/Builds/WebGL/* backend/static/unity/
```

### 5. Integrate into React App

#### Add the Unity Component

Copy `web_dice_game_component.tsx` to your React components folder and import it:

```typescript
import UnityDiceGame from './components/UnityDiceGame';
```

#### Create a Game Page

Use the sample `DiceGamePage.tsx` as a starting point. Here's the key integration:

```typescript
const [diceResults, setDiceResults] = useState<number[]>([]);
const unityGameRef = useRef<any>(null);

const handleDiceRollComplete = (results: number[]) => {
  setDiceResults(results);
  // Process results, calculate winnings, etc.
};

return (
  <UnityDiceGame
    ref={unityGameRef}
    onDiceRollComplete={handleDiceRollComplete}
    width={960}
    height={600}
  />
);
```

#### Control the Unity Game

```typescript
// Roll specific dice values
unityGameRef.current?.rollDice([1, 3, 5, 2, 6, 4]);

// Start shake animation
unityGameRef.current?.startShakeAnimation();

// Reset the game
unityGameRef.current?.resetDice();
```

## Communication Flow

### Unity → React
- `OnDiceRollComplete(results)` - Called when dice rolling animation completes
- `OnGameStateChanged(state)` - Called when game state changes ("rolling", "completed", etc.)
- `SendMessageToReact(message)` - Generic message channel

### React → Unity
- `RollDice(values)` - Trigger dice roll with specific values
- `StartShakeAnimation()` - Start the dice shaking animation
- `ResetDice()` - Reset dice to initial state
- `UpdateGameState(state)` - Update game state

## Browser Compatibility

- **Supported**: Chrome 80+, Firefox 75+, Safari 13+, Edge 80+
- **Not Supported**: Mobile browsers (iOS Safari has limitations)
- **Requirements**: WebGL 2.0 support

## Performance Considerations

1. **Memory**: WebGL builds use more memory than native apps
2. **Loading**: Initial load may take time due to large asset files
3. **Mobile**: Not recommended for mobile devices due to performance and compatibility issues

## Troubleshooting

### Build Issues
- Ensure all scenes are added to Build Settings
- Check that WebGL platform is installed in Unity
- Verify output directory permissions

### Runtime Issues
- Check browser console for WebGL errors
- Ensure WebGL is enabled in browser settings
- Verify all asset files are accessible via HTTP

### Communication Issues
- Check that global functions are defined before Unity loads
- Verify function signatures match between Unity and JavaScript
- Use browser developer tools to debug communication

## Development vs Production

### Development Build
Use the development build for debugging:
```csharp
[MenuItem("Build/Build WebGL Development")]
public static void BuildWebGLDevelopment()
{
    // Includes profiler connection and debug symbols
}
```

### Production Build
Use the regular build for production:
- Smaller file size
- Better performance
- No debug overhead

## Next Steps

1. Test the integration with your existing backend API
2. Add betting logic to communicate with your Django backend
3. Implement real-time updates using WebSocket connections
4. Add responsive design for different screen sizes
5. Optimize assets for faster loading

## File Structure After Integration

```
backend/static/
├── unity/
│   ├── index.html
│   ├── Build/
│   │   ├── WebGL.data
│   │   ├── WebGL.framework.js
│   │   ├── WebGL.wasm
│   │   └── WebGL.loader.js
│   └── TemplateData/
│       ├── style.css
│       └── favicon.ico
└── react/
    └── (existing React build files)
```

The Unity WebGL build will now run alongside your existing React application, providing the same dice rolling experience in the browser as in your Android app.