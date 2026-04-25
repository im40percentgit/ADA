/**
 * useSolitaire — React hook wrapping the Klondike engine with undo support
 * and per-move telemetry (M1 v0.5).
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
 * Telemetry (M1 v0.5):
 * - `lastRenderTime` ref tracks when the last state became visible to the
 *   patient. It is updated synchronously after each dispatch (useReducer
 *   is synchronous) so the next move's decision_time_ms measures from the
 *   correct baseline.
 * - `recordMoveMade()` is called after each action that modifies game state.
 *   Undo counts as a move (was_undo=true). Invalid moves return a state
 *   with higher errorCount — we detect validity by comparing errorCount.
 *
 * @decision DEC-GAMES-001
 * @title useSolitaire wraps the pure engine — no game logic in this file
 * @status accepted
 * @rationale Separation of engine (pure functions) from hook (React state)
 *   keeps the engine fully unit-testable without React. The hook owns only
 *   the history stack, action dispatch, and telemetry coordination.
 *
 * @decision DEC-GAMES-007
 * @title decision_time_ms measured from last render commit
 * @status accepted
 * @rationale lastRenderTime is set to Date.now() after each dispatch so the
 *   measurement matches when the patient saw the new game state.
 *
 * @decision DEC-GAMES-025
 * @title Double-click auto-move audio gated on actual move success
 * @status accepted
 * @rationale Founder reported the 'move' sound playing even when double-clicking
 *   a card with no valid foundation target. Root cause: autoMoveAny() (formerly
 *   autoMoveToFoundation()) calls applyMove() which returns { ...state, errorCount+1 }
 *   (not null) for an illegal placement — so the speculative result was non-null and
 *   play() fired unconditionally. Fix: check specAutoNext.errorCount === prevGame.errorCount
 *   (same validity pattern as move()), and only play sound when the move was
 *   actually applied. No sound plays on failed auto-move; the card simply
 *   doesn't move, which is clear enough feedback without a shake animation.
 *
 * @decision DEC-GAMES-028
 * @title Auto-move telemetry records actual resolved destination
 * @status accepted
 * @rationale Previously autoMove hardcoded a foundation target for recordMoveMade,
 *   mislabeling tableau-to-tableau auto-moves in calibration data. Now we call
 *   findAutoMoveTarget() for the real target, then pass it to getMoveType() so
 *   move_type reflects the actual path taken (talon-to-tableau, tableau-to-tableau, etc.).
 */

import { useCallback, useReducer, useRef } from 'react'
import {
  applyMove,
  autoMoveAny,
  findAutoMoveTarget,
  drawFromStock,
  getMoveType,
  getMovedCardValue,
  newGame,
} from './engine'
import { recordMoveMade } from './telemetry'
import { play } from './audio'
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
      const next = autoMoveAny(state.game, action.source)
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

  /**
   * Tracks when the last game state became visible to the patient.
   * Set to Date.now() after every dispatch that produces a new game state.
   * Initialized to Date.now() at hook mount (session start time baseline).
   */
  const lastRenderTime = useRef<number>(Date.now())

  // Stable ref to current game state — used inside callbacks without
  // causing them to re-create on every render (avoids stale closure issues).
  const stateRef = useRef(state)
  stateRef.current = state

  const deal = useCallback(() => {
    dispatch({ type: 'DEAL' })
    play('shuffle')
  }, [])

  const draw = useCallback(() => {
    const prevGame = stateRef.current.game
    const decisionTimeMs = Date.now() - lastRenderTime.current
    dispatch({ type: 'DRAW' })
    lastRenderTime.current = Date.now()

    // Determine if this was a recycle (stock was empty → talon recycled)
    const wasRecycle = prevGame.stock.cards.length === 0
    play(wasRecycle ? 'shuffle' : 'flip')
    void recordMoveMade({
      moveType: wasRecycle ? 'recycle' : 'stock-flip',
      wasValid: true,
      wasUndo: false,
      decisionTimeMs,
      cardValue: null,
    })
  }, [])

  const move = useCallback(
    (source: CardSource, target: CardTarget) => {
      const prevGame = stateRef.current.game
      const decisionTimeMs = Date.now() - lastRenderTime.current
      const cardValue = getMovedCardValue(prevGame, source)
      dispatch({ type: 'MOVE', source, target })
      lastRenderTime.current = Date.now()

      // Detect validity: applyMove returns state with higher errorCount for invalid moves
      // We can't see the next state here synchronously after dispatch (useReducer is async
      // in the sense that stateRef.current doesn't update until next render). Instead,
      // we call applyMove speculatively just to check legality — same args, no side effects.
      const specNext = applyMove(prevGame, source, target)
      const wasValid = specNext !== null && specNext.errorCount === prevGame.errorCount
      if (wasValid) {
        // Play 'move' as the primary feedback. Tableau auto-flip (if any) is
        // a secondary effect — we deliberately avoid a double-fire by not
        // playing 'flip' here; the move swoosh is the dominant UX signal.
        if (specNext?.won) {
          play('win')
        } else {
          play('move')
        }
      }
      void recordMoveMade({
        moveType: getMoveType(source, target),
        wasValid,
        wasUndo: false,
        decisionTimeMs,
        cardValue,
      })
    },
    [],
  )

  const autoMove = useCallback(
    (source: CardSource) => {
      const prevGame = stateRef.current.game
      const decisionTimeMs = Date.now() - lastRenderTime.current
      const cardValue = getMovedCardValue(prevGame, source)
      dispatch({ type: 'AUTO_MOVE', source })
      lastRenderTime.current = Date.now()

      // Resolve the actual target so telemetry records the real destination
      // (e.g. tableau-to-tableau), not a hardcoded foundation type.
      //
      // @decision DEC-GAMES-028
      // @title Auto-move telemetry records actual resolved destination
      // @status accepted
      // @rationale Hardcoding a foundation target in recordMoveMade mislabels
      //   tableau-to-tableau auto-moves in calibration data. findAutoMoveTarget
      //   runs the same resolution logic as autoMoveAny, giving us the real
      //   target for telemetry without changing the reducer's state contract.
      const resolvedTarget = findAutoMoveTarget(prevGame, source)

      // Speculate the outcome to gate audio on actual success.
      // autoMoveAny returns { ...state, errorCount+1 } for no-destination (not null),
      // so we check errorCount to distinguish a valid move from a failed one.
      const specAutoNext = autoMoveAny(prevGame, source)
      const wasValid = specAutoNext !== null && specAutoNext.errorCount === prevGame.errorCount
      if (wasValid) {
        if (specAutoNext!.won) {
          play('win')
        } else {
          play('move')
        }
      }
      void recordMoveMade({
        moveType: getMoveType(source, resolvedTarget),
        wasValid,
        wasUndo: false,
        decisionTimeMs,
        cardValue,
      })
    },
    [],
  )

  const undo = useCallback(() => {
    const decisionTimeMs = Date.now() - lastRenderTime.current
    dispatch({ type: 'UNDO' })
    lastRenderTime.current = Date.now()

    void recordMoveMade({
      moveType: 'invalid',  // undo has no source/target — type is informational
      wasValid: true,
      wasUndo: true,
      decisionTimeMs,
      cardValue: null,
    })
  }, [])

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
