import React, { useEffect, useRef, useState } from 'react';

interface UnityDiceGameProps {
  onDiceRollComplete?: (results: number[]) => void;
  onGameStateChange?: (state: string) => void;
  width?: number;
  height?: number;
}

declare global {
  interface Window {
    createUnityInstance: (canvas: HTMLCanvasElement, config: any, onProgress?: (progress: number) => void) => Promise<any>;
    unityInstance: any;
  }
}

const UnityDiceGame: React.FC<UnityDiceGameProps> = ({
  onDiceRollComplete,
  onGameStateChange,
  width = 800,
  height = 600
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const unityInstanceRef = useRef<any>(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState(0);

  useEffect(() => {
    // Unity WebGL communication functions
    window.OnDiceRollComplete = (resultsString: string) => {
      const results = resultsString.split(',').map(Number);
      onDiceRollComplete?.(results);
    };

    window.OnGameStateChanged = (state: string) => {
      onGameStateChange?.(state);
    };

    window.SendMessageToReact = (message: string) => {
      console.log('Unity message:', message);
    };

    return () => {
      // Cleanup
      if (unityInstanceRef.current) {
        unityInstanceRef.current.Quit();
      }
    };
  }, [onDiceRollComplete, onGameStateChange]);

  useEffect(() => {
    const loadUnityGame = async () => {
      if (!canvasRef.current) return;

      try {
        const unityInstance = await window.createUnityInstance(
          canvasRef.current,
          {
            dataUrl: "/unity/Build/WebGL.data",
            frameworkUrl: "/unity/Build/WebGL.framework.js",
            codeUrl: "/unity/Build/WebGL.wasm",
            streamingAssetsUrl: "/unity/StreamingAssets",
            companyName: "YourCompany",
            productName: "DiceGame",
            productVersion: "1.0",
          },
          (progress: number) => {
            setLoadingProgress(progress);
          }
        );

        unityInstanceRef.current = unityInstance;
        setIsLoaded(true);
      } catch (error) {
        console.error('Failed to load Unity game:', error);
      }
    };

    loadUnityGame();
  }, []);

  // Public methods to control the Unity game
  const rollDice = (diceValues: number[]) => {
    if (unityInstanceRef.current) {
      const valuesString = diceValues.join(',');
      unityInstanceRef.current.SendMessage('WebGLBridge', 'RollDice', valuesString);
    }
  };

  const startShakeAnimation = () => {
    if (unityInstanceRef.current) {
      unityInstanceRef.current.SendMessage('WebGLBridge', 'StartShakeAnimation');
    }
  };

  const resetDice = () => {
    if (unityInstanceRef.current) {
      unityInstanceRef.current.SendMessage('WebGLBridge', 'ResetDice');
    }
  };

  const updateGameState = (state: string) => {
    if (unityInstanceRef.current) {
      unityInstanceRef.current.SendMessage('WebGLBridge', 'UpdateGameState', state);
    }
  };

  // Expose methods to parent component
  React.useImperativeHandle(ref, () => ({
    rollDice,
    startShakeAnimation,
    resetDice,
    updateGameState
  }));

  if (!isLoaded) {
    return (
      <div style={{ width, height, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#000' }}>
        <div style={{ textAlign: 'center', color: '#fff' }}>
          <div>Loading Unity Game...</div>
          <div style={{ width: '200px', height: '20px', backgroundColor: '#333', margin: '10px auto' }}>
            <div
              style={{
                width: `${loadingProgress * 100}%`,
                height: '100%',
                backgroundColor: '#4CAF50',
                transition: 'width 0.3s ease'
              }}
            />
          </div>
          <div>{Math.round(loadingProgress * 100)}%</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ width, height }}>
      <canvas
        ref={canvasRef}
        style={{
          width: '100%',
          height: '100%',
          backgroundColor: '#000'
        }}
        tabIndex={-1}
      />
    </div>
  );
};

export default React.forwardRef(UnityDiceGame);

// Global functions for Unity to call
declare global {
  function OnDiceRollComplete(results: string): void;
  function OnGameStateChanged(state: string): void;
  function SendMessageToReact(message: string): void;
}