import React, { useRef, useState, useEffect } from 'react';
import UnityDiceGame from './UnityDiceGame';

const DiceGamePage: React.FC = () => {
  const unityGameRef = useRef<any>(null);
  const [diceResults, setDiceResults] = useState<number[]>([]);
  const [gameState, setGameState] = useState<string>('waiting');
  const [betAmount, setBetAmount] = useState<string>('10');
  const [selectedNumbers, setSelectedNumbers] = useState<Set<number>>(new Set());
  const [recentResults, setRecentResults] = useState<any[]>([]);

  // Fetch recent results on mount and when a round completes
  const fetchRecentResults = async () => {
    try {
      const response = await fetch('/api/game/recent-round-results/?count=3');
      if (response.ok) {
        const data = await response.json();
        setRecentResults(data);
      }
    } catch (error) {
      console.error('Failed to fetch recent results:', error);
    }
  };

  useEffect(() => {
    fetchRecentResults();
  }, []);

  const handleDiceRollComplete = (results: number[]) => {
    setDiceResults(results);
    setGameState('completed');

    // Calculate winnings based on bets
    const winnings = calculateWinnings(results, selectedNumbers, parseFloat(betAmount));
    console.log('Dice results:', results);
    console.log('Winnings:', winnings);
    
    // Refresh recent results after a short delay to allow backend to process
    setTimeout(fetchRecentResults, 2000);
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

      {/* Recent Results - Scrollable Section */}
      <div style={{ marginTop: '30px', padding: '20px', backgroundColor: '#2a2a2a', borderRadius: '10px' }}>
        <h2 style={{ color: '#FF9800', marginBottom: '15px' }}>Recent Round Results</h2>
        <div style={{ 
          maxHeight: '300px', 
          overflowY: 'auto', 
          padding: '10px',
          border: '1px solid #444',
          borderRadius: '8px',
          backgroundColor: '#1a1a1a'
        }}>
          {recentResults.length > 0 ? (
            recentResults.map((result, index) => (
              <div key={result.round_id} style={{ 
                padding: '15px', 
                borderBottom: index < recentResults.length - 1 ? '1px solid #333' : 'none',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <div>
                  <div style={{ fontWeight: 'bold', color: '#4CAF50' }}>Round: {result.round_id}</div>
                  <div style={{ fontSize: '12px', color: '#888' }}>{new Date(result.timestamp).toLocaleString()}</div>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {[1, 2, 3, 4, 5, 6].map(i => (
                    <div key={i} style={{ 
                      width: '30px', 
                      height: '30px', 
                      backgroundColor: '#333', 
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '14px',
                      fontWeight: 'bold',
                      border: '1px solid #555'
                    }}>
                      {result[`dice_${i}`]}
                    </div>
                  ))}
                </div>
                <div style={{ fontWeight: 'bold', color: '#FF9800' }}>
                  Result: {result.dice_result}
                </div>
              </div>
            ))
          ) : (
            <div style={{ textAlign: 'center', padding: '20px', color: '#888' }}>
              No recent results found.
            </div>
          )}
        </div>
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