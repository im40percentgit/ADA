/**
 * useSolitaire — React hook wrapping the Klondike engine with undo support.
 *
 * State management:
 * - `game` is the current GameState snapshot (immutable)
 * - `history` is a stack of prior GameState snapshots for undo
 * - All mutations create new snapshots — no in-place mutation
 *
 * Undo design: value-type move history per DEC-UNDO-001 from the Swift
 * project. Rather than recording the move itself (which requires re-playing),
 * we store the full prior GameState. At N=1 and 52 cards per snapshot the
 * memory cost is negligible and the undo logic is trivially correct.
 *
 * @decision DEC-GAMES-001
 * @title useSolitaire wraps the pure engine — no game logic in this file
 * @status accepted
 * @rationale Separation of engine (pure functions) from hook (React state)
 *   keeps the engine fully unit-testable without React. The hook owns only
 *   the history stack and action dispatch.
 */

import { useCallback, useReducer } from 'react'
import {
  applyMove,
  autoMoveToFoundation,
  drawFromStock,
  newGame,
} from './engine'
import type { CardSource, CardTarget, DeckStyle, GameState } from './types'

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

interface SolitaireState {
  game: GameState
  /** Stack of prior GameStates for undo. */
  history: GameState[]
  /** Completed hands in this game session (wins). */
  completedHands: number
  deckStyle: DeckStyle
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

type Action =
  | { type: 'DEAL' }
  | { type: 'DRAW' }
  | { type: 'MOVE'; source: CardSource; target: CardTarget }
  | { type: 'AUTO_MOVE'; source: CardSource }
  | { type: 'UNDO' }
  | { type: 'SET_DECK'; style: DeckStyle }

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

function reducer(state: SolitaireState, action: Action): SolitaireState {
  switch (action.type) {
    case 'DEAL': {
      return {
        ...state,
        game: newGame(),
        history: [],
      }
    }

    case 'DRAW': {
      const next = drawFromStock(state.game)
      return {
        ...state,
        game: next,
        history: [...state.history, state.game],
      }
    }

    case 'MOVE': {
      const next = applyMove(state.game, action.source, action.target)
      if (next === null) return state   // Illegal — no state change
      const won = next.won && !state.game.won
      return {
        ...state,
        game: next,
        history: [...state.history, state.game],
        completedHands: won ? state.completedHands + 1 : state.completedHands,
      }
    }

    case 'AUTO_MOVE': {
      const next = autoMoveToFoundation(state.game, action.source)
      if (next === null) return state
      const won = next.won && !state.game.won
      return {
        ...state,
        game: next,
        history: [...state.history, state.game],
        completedHands: won ? state.completedHands + 1 : state.completedHands,
      }
    }

    case 'UNDO': {
      if (state.history.length === 0) return state
      const prev = state.history[state.history.length - 1]
      return {
        ...state,
        game: prev,
        history: state.history.slice(0, -1),
      }
    }

    case 'SET_DECK': {
      return { ...state, deckStyle: action.style }
    }

    default:
      return state
  }
}

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

function makeInitial(deckStyle: DeckStyle): SolitaireState {
  return {
    game: newGame(),
    history: [],
    completedHands: 0,
    deckStyle,
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseSolitaireReturn {
  game: GameState
  history: GameState[]
  completedHands: number
  deckStyle: DeckStyle
  canUndo: boolean
  deal: () => void
  draw: () => void
  move: (source: CardSource, target: CardTarget) => void
  autoMove: (source: CardSource) => void
  undo: () => void
  setDeckStyle: (style: DeckStyle) => void
}

export function useSolitaire(initialDeck: DeckStyle = 'corgi'): UseSolitaireReturn {
  const [state, dispatch] = useReducer(reducer, initialDeck, makeInitial)

  const deal = useCallback(() => dispatch({ type: 'DEAL' }), [])
  const draw = useCallback(() => dispatch({ type: 'DRAW' }), [])
  const move = useCallback(
    (source: CardSource, target: CardTarget) =>
      dispatch({ type: 'MOVE', source, target }),
    [],
  )
  const autoMove = useCallback(
    (source: CardSource) => dispatch({ type: 'AUTO_MOVE', source }),
    [],
  )
  const undo = useCallback(() => dispatch({ type: 'UNDO' }), [])
  const setDeckStyle = useCallback(
    (style: DeckStyle) => dispatch({ type: 'SET_DECK', style }),
    [],
  )

  return {
    game: state.game,
    history: state.history,
    completedHands: state.completedHands,
    deckStyle: state.deckStyle,
    canUndo: state.history.length > 0,
    deal,
    draw,
    move,
    autoMove,
    undo,
    setDeckStyle,
  }
}
