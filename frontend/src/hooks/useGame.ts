import { useContext } from 'react';
import { GameContext, type GameContextValue } from '../context/GameContext';

/**
 * Convenience hook for consuming GameContext.
 * Throws if used outside of a GameProvider.
 */
export function useGame(): GameContextValue {
  const context = useContext(GameContext);
  if (!context) {
    throw new Error('useGame must be used within a GameProvider');
  }
  return context;
}
