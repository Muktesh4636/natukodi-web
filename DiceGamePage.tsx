import React, { useRef, useState } from 'react';
import UnityDiceGame from './UnityDiceGame';

const DiceGamePage: React.FC = () => {
  const unityGameRef = useRef<any>(null);
  const [diceResults, setDiceResults] = useState<number[]>([]);
  const [gameState, setGameState] = useState<string>('waiting');
  const [betAmount, setBetAmount] = useState<string>('10');
  const [selectedNumbers, setSelectedNumbers] = useState<Set<number>>(new Set());

  const handleDiceRollComplete = (results: number[]) => {
    setDiceResults(results);
    setGameState('completed');

    // Calculate winnings based on bets
    const winnings = calculateWinnings(results, selectedNumbers, parseFloat(betAmount));
    console.log('Dice results:', results);
    console.log('Winnings:', winnings);
  };

  const handleGameStateChange = (state: string) => {
    setGameState(state);
  };

  const calculateWinnings = (results: number[], bets: Set<number>, amount: number): number => {
    let totalWinnings = 0;
    results.forEach(die => {
      if (bets.has(die)) {
        totalWinnings += amount * 2; // Simple 2x multiplier for demo
      }
    });
    return totalWinnings;
  };

  const handleRollDice = () => {
    if (unityGameRef.current) {
      // Generate random dice results (in real app, this comes from server)
      const randomResults = Array.from({ length: 6 }, () => Math.floor(Math.random() * 6) + 1);
      unityGameRef.current.rollDice(randomResults);
    }
  };

  const handleShakeDice = () => {
    if (unityGameRef.current) {
      unityGameRef.current.startShakeAnimation();
    }
  };

  const handleResetDice = () => {
    if (unityGameRef.current) {
      unityGameRef.current.resetDice();
      setDiceResults([]);
      setGameState('waiting');
      setSelectedNumbers(new Set());
    }
  };

  const toggleNumberSelection = (number: number) => {
    const newSelection = new Set(selectedNumbers);
    if (newSelection.has(number)) {
      newSelection.delete(number);
    } else {
      newSelection.add(number);
    }
    setSelectedNumbers(newSelection);
  };

  return (
    <div style={{ padding: '20px', backgroundColor: '#1a1a1a', minHeight: '100vh', color: 'white' }}>
      <h1>Dice Game</h1>

      {/* Game Controls */}
      <div style={{ marginBottom: '20px' }}>
        <h2>Place Your Bets</h2>
        <div style={{ marginBottom: '10px' }}>
          <label>Bet Amount: </label>
          <input
            type="number"
            value={betAmount}
            onChange={(e) => setBetAmount(e.target.value)}
            style={{ marginLeft: '10px', padding: '5px' }}
          />
        </div>

        <div style={{ marginBottom: '10px' }}>
          <label>Select Numbers (1-6): </label>
          {[1, 2, 3, 4, 5, 6].map(number => (
            <button
              key={number}
              onClick={() => toggleNumberSelection(number)}
              style={{
                margin: '0 5px',
                padding: '5px 10px',
                backgroundColor: selectedNumbers.has(number) ? '#4CAF50' : '#333',
                color: 'white',
                border: 'none',
                borderRadius: '5px',
                cursor: 'pointer'
              }}
            >
              {number}
            </button>
          ))}
        </div>

        <div>
          <button
            onClick={handleShakeDice}
            disabled={gameState === 'rolling'}
            style={{
              margin: '0 10px',
              padding: '10px 20px',
              backgroundColor: gameState === 'rolling' ? '#666' : '#FF9800',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: gameState === 'rolling' ? 'not-allowed' : 'pointer'
            }}
          >
            Shake Dice
          </button>

          <button
            onClick={handleRollDice}
            disabled={gameState === 'rolling' || selectedNumbers.size === 0}
            style={{
              margin: '0 10px',
              padding: '10px 20px',
              backgroundColor: gameState === 'rolling' || selectedNumbers.size === 0 ? '#666' : '#2196F3',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: gameState === 'rolling' || selectedNumbers.size === 0 ? 'not-allowed' : 'pointer'
            }}
          >
            Roll Dice
          </button>

          <button
            onClick={handleResetDice}
            style={{
              margin: '0 10px',
              padding: '10px 20px',
              backgroundColor: '#f44336',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer'
            }}
          >
            Reset Game
          </button>
        </div>
      </div>

      {/* Game Status */}
      <div style={{ marginBottom: '20px' }}>
        <h3>Game Status: {gameState}</h3>
        {diceResults.length > 0 && (
          <div>
            <h3>Dice Results: {diceResults.join(', ')}</h3>
            <h3>Potential Winnings: ₹{calculateWinnings(diceResults, selectedNumbers, parseFloat(betAmount))}</h3>
          </div>
        )}
      </div>

      {/* Unity Game */}
      <div style={{ border: '2px solid #333', borderRadius: '10px', overflow: 'hidden' }}>
        <UnityDiceGame
          ref={unityGameRef}
          onDiceRollComplete={handleDiceRollComplete}
          onGameStateChange={handleGameStateChange}
          width={960}
          height={600}
        />
      </div>

      {/* Instructions */}
      <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#333', borderRadius: '5px' }}>
        <h3>How to Play:</h3>
        <ol>
          <li>Select numbers (1-6) you want to bet on</li>
          <li>Enter your bet amount</li>
          <li>Click "Shake Dice" to start the animation</li>
          <li>Click "Roll Dice" to reveal the results</li>
          <li>If your selected numbers appear, you win!</li>
        </ol>
      </div>
    </div>
  );
};

export default DiceGamePage;