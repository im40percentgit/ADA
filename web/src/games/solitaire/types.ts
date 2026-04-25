/**
 * Solitaire domain types — pure value types, no React.
 *
 * All game state is represented as plain objects so the engine can be
 * tested without a DOM and the history stack can use structural equality.
 *
 * Card values 1–52 map to: Spades 1-13, Hearts 14-26, Diamonds 27-39, Clubs 40-52.
 * Aces are rank 1; Kings are rank 13.
 */

export type Suit = 'spades' | 'hearts' | 'diamonds' | 'clubs'
export type Color = 'red' | 'black'

/** A playing card. Immutable value type — never mutate; always replace. */
export interface Card {
  /** 1–52. Encodes both suit and rank: Math.ceil(value / 13) = suit index (1-4). */
  readonly value: number
  readonly suit: Suit
  /** 1 = Ace, 13 = King */
  readonly rank: number
  readonly color: Color
  readonly faceUp: boolean
}

/** Which deck artwork to use. Persisted to localStorage. */
export type DeckStyle = 'corgi' | 'classic'

/** A pile of cards — used for tableau columns, foundations, stock, and talon. */
export interface Pile {
  readonly cards: readonly Card[]
}

/** Complete Klondike game state. Immutable snapshot — replace, never mutate. */
export interface GameState {
  /** 7 tableau columns (index 0–6). */
  readonly tableau: readonly Pile[]
  /** 4 foundation piles — one per suit, built A→K. */
  readonly foundations: readonly Pile[]
  /** Undealt stock pile (face-down). */
  readonly stock: Pile
  /** Talon — cards turned over from stock; top card is playable. */
  readonly talon: Pile
  /** True once all 52 cards are on foundations. */
  readonly won: boolean
  /** Count of invalid move attempts in this session. */
  readonly errorCount: number
}

/** A move record for the undo stack. Value type — no DOM refs. */
export interface MoveRecord {
  readonly before: GameState
}

/** Where a card (or run of cards) came from. */
export interface CardSource {
  readonly type: 'tableau' | 'talon' | 'foundation'
  /** Column/foundation index (0-based). For talon, always 0. */
  readonly pileIndex: number
  /** Index of the card within the pile (for tableau — top of a run). */
  readonly cardIndex: number
}

/** Where a card (or run) is being dropped. */
export interface CardTarget {
  readonly type: 'tableau' | 'foundation'
  readonly pileIndex: number
}
