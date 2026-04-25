/**
 * Klondike Solitaire game engine — pure functions, no React, no DOM.
 *
 * All functions take a GameState and return a new GameState (or boolean/null).
 * Nothing is mutated. The history stack in useSolitaire stores GameState
 * snapshots for undo.
 *
 * Rules implemented:
 * - Standard Klondike: deal 1 card from stock (draw-1 mode)
 * - Tableau: alternating color, descending rank; runs can be moved
 * - Foundation: same suit, ascending rank starting from Ace
 * - Empty tableau column: only Kings (rank 13)
 * - Empty foundation: only Aces (rank 1)
 * - Win: all 52 cards on foundations
 * - Foundation→Tableau: top card of any foundation can be moved back to tableau
 *
 * @decision DEC-GAMES-001
 * @title Solitaire engine is a pure TS module, not a port of Swift UIKit code
 * @status accepted
 * @rationale The Swift game is UIKit/MVC with shared singletons — not portable.
 *   A clean React-idiomatic re-implementation is shorter, testable, and avoids
 *   carrying over the Swift multitouch race bugs. The Swift code is reference spec.
 *
 * @decision DEC-GAMES-024
 * @title Foundation cards can be moved back to tableau
 * @status accepted
 * @rationale Standard Klondike rule: the top card of any foundation pile may be
 *   dragged back to a tableau column if it forms a legal alternating-color
 *   descending sequence. This is essential when a card is needed to bridge a
 *   tableau column during play. Foundation-to-foundation moves are NOT supported
 *   (same suit ascending order means the only legal target would be itself, which
 *   is a no-op). A new 'foundation-to-tableau' MoveType is added for telemetry.
 */

import type { Card, CardSource, CardTarget, GameState, Pile, Suit } from './types'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SUITS: Suit[] = ['spades', 'hearts', 'diamonds', 'clubs']

// ---------------------------------------------------------------------------
// Card construction helpers
// ---------------------------------------------------------------------------

/** Compute the 1-based card value from suit index (0-3) and rank (1-13). */
export function cardValue(suitIndex: number, rank: number): number {
  return suitIndex * 13 + rank
}

/** Build a Card from its 1-52 value. */
export function makeCard(value: number, faceUp = false): Card {
  const suitIndex = Math.floor((value - 1) / 13)   // 0-3
  const rank = ((value - 1) % 13) + 1               // 1-13
  const suit = SUITS[suitIndex]
  const color = suit === 'hearts' || suit === 'diamonds' ? 'red' : 'black'
  return { value, suit, rank, color, faceUp }
}

/**
 * Return the corgi image path for a card value (1–52).
 *
 * Used for face-DOWN cards when deck === 'corgi'. Each of the 52 cards maps
 * deterministically to its own corgi JPG, matching SwiftSolitaire
 * CardBackManager.image(forCardValue:).
 *
 * @decision DEC-GAMES-009
 * @title Corgi photos are card backs only, never face-up art
 * @status accepted
 * @rationale Matches original SwiftSolitaire CardBackManager: corgi JPGs are
 *   rendered on face-down cards only. Face-up cards always show standard
 *   rank+suit art so the patient can always read what card is showing.
 */
export function corgiImagePath(value: number): string {
  const idx = ((value - 1) % 52) + 1
  return `/games/solitaire/corgi/corgi-${String(idx).padStart(2, '0')}.jpg`
}

/**
 * Return the classic card back image path (used when deck === 'classic').
 *
 * @decision DEC-GAMES-009
 * @title Classic back is always PlayingCard-back.png
 * @status accepted
 * @rationale Single shared back for classic mode, matching SwiftSolitaire's
 *   CardBackManager.imageForStyle(.classic) which returns one shared image.
 */
export function classicBackPath(): string {
  return '/games/solitaire/classic/PlayingCard-back.png'
}

/**
 * Return the standard playing-card face image path for a card, or null when
 * no image asset exists for this rank (numeric ranks 3–10 use CSS rendering).
 *
 * Asset naming matches the normalized copies from SwiftSolitaire/images/:
 *   Ace   → /games/solitaire/classic/{Suit}-A.png
 *   2     → /games/solitaire/classic/{Suit}-2.png
 *   J/Q/K → /games/solitaire/classic/{Suit}-{J|Q|K}.png
 *   3–10  → null (caller falls back to styled CSS text face)
 *
 * @decision DEC-GAMES-010
 * @title Standard playing-card art shared by both deck modes for face-up cards
 * @status accepted
 * @rationale Gameplay must show rank/suit clearly regardless of deck-back
 *   personalization. Corgi mode only changes the card back (face-down), never
 *   the face-up art. Matches original SwiftSolitaire behavior where face-up
 *   cards always use the same standard art regardless of CardBackStyle.
 */
export function classicImagePath(card: Card): string | null {
  const rankName: string | null =
    card.rank === 1  ? 'A' :
    card.rank === 2  ? '2' :
    card.rank === 11 ? 'J' :
    card.rank === 12 ? 'Q' :
    card.rank === 13 ? 'K' :
    null
  if (rankName === null) return null  // ranks 3–10: no image asset, use CSS
  // @decision DEC-GAMES-019
  // @title classicImagePath suit name — drop trailing 's' (Suit type is already plural)
  // @status accepted
  // @rationale Suit values are 'spades'|'hearts'|'diamonds'|'clubs' (already plural).
  //   Original code appended '+ s' producing 'Spadess', 'Heartss', etc., which 404'd
  //   against files named 'Spades-A.png'. Removing the suffix produces the correct
  //   capitalised-first-letter form that matches the asset filenames on disk.
  const suitName = card.suit.charAt(0).toUpperCase() + card.suit.slice(1)
  return `/games/solitaire/classic/${suitName}-${rankName}.png`
}

// ---------------------------------------------------------------------------
// Deck / deal
// ---------------------------------------------------------------------------

/** Build and shuffle a standard 52-card deck (Fisher-Yates). */
export function buildShuffledDeck(): Card[] {
  const deck: Card[] = []
  for (let v = 1; v <= 52; v++) {
    deck.push(makeCard(v, false))
  }
  // Fisher-Yates
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[deck[i], deck[j]] = [deck[j], deck[i]]
  }
  return deck
}

/**
 * Deal a new Klondike game from the given deck.
 * Column i gets i+1 cards (i=0..6), top card face-up.
 */
export function dealGame(deck: Card[]): GameState {
  const tableau: Pile[] = []
  let idx = 0
  for (let col = 0; col < 7; col++) {
    const cards: Card[] = []
    for (let row = 0; row <= col; row++) {
      const card = deck[idx++]
      cards.push({ ...card, faceUp: row === col })
    }
    tableau.push({ cards })
  }
  const stock: Card[] = deck.slice(idx).map(c => ({ ...c, faceUp: false }))
  return {
    tableau,
    foundations: [
      { cards: [] },
      { cards: [] },
      { cards: [] },
      { cards: [] },
    ],
    stock: { cards: stock },
    talon: { cards: [] },
    won: false,
    errorCount: 0,
  }
}

/** Create a fresh dealt game using a freshly shuffled deck. */
export function newGame(): GameState {
  return dealGame(buildShuffledDeck())
}

// ---------------------------------------------------------------------------
// Move legality
// ---------------------------------------------------------------------------

/** Can card be placed on top of targetTop in a tableau column? */
export function canPlaceOnTableau(card: Card, targetTop: Card | null): boolean {
  if (targetTop === null) {
    // Empty column — only Kings
    return card.rank === 13
  }
  return targetTop.faceUp &&
    card.color !== targetTop.color &&
    card.rank === targetTop.rank - 1
}

/** Can card be placed on the foundation for its suit? */
export function canPlaceOnFoundation(card: Card, foundation: Pile): boolean {
  if (foundation.cards.length === 0) {
    return card.rank === 1  // Ace starts foundation
  }
  const top = foundation.cards[foundation.cards.length - 1]
  return card.suit === top.suit && card.rank === top.rank + 1
}

/** Which foundation pile index does this card's suit map to? */
export function foundationIndexForSuit(suit: Suit): number {
  return SUITS.indexOf(suit)
}

// ---------------------------------------------------------------------------
// Move execution helpers
// ---------------------------------------------------------------------------

function setPile(piles: readonly Pile[], index: number, pile: Pile): Pile[] {
  return piles.map((p, i) => (i === index ? pile : p))
}

function flipTopCard(pile: Pile): Pile {
  if (pile.cards.length === 0) return pile
  const cards = [...pile.cards]
  cards[cards.length - 1] = { ...cards[cards.length - 1], faceUp: true }
  return { cards }
}

// ---------------------------------------------------------------------------
// Public move actions — each returns a new GameState or null if illegal
// ---------------------------------------------------------------------------

/**
 * Draw one card from stock to talon.
 * If stock is empty, recycle talon back to stock (face-down).
 */
export function drawFromStock(state: GameState): GameState {
  if (state.stock.cards.length === 0) {
    // Recycle talon → stock
    const recycled = [...state.talon.cards].reverse().map(c => ({ ...c, faceUp: false }))
    return { ...state, stock: { cards: recycled }, talon: { cards: [] } }
  }
  const stockCards = [...state.stock.cards]
  const drawn = { ...stockCards.pop()!, faceUp: true }
  return {
    ...state,
    stock: { cards: stockCards },
    talon: { cards: [...state.talon.cards, drawn] },
  }
}

/**
 * Move a card (or run of cards) from source to target.
 * Returns null if the move is illegal.
 */
export function applyMove(
  state: GameState,
  source: CardSource,
  target: CardTarget,
): GameState | null {
  // --- Extract the cards being moved ---
  let movingCards: Card[]
  let newSource: GameState

  if (source.type === 'talon') {
    const talon = state.talon
    if (talon.cards.length === 0) return null
    const top = talon.cards[talon.cards.length - 1]
    movingCards = [top]
    newSource = {
      ...state,
      talon: { cards: talon.cards.slice(0, -1) },
    }
  } else if (source.type === 'tableau') {
    const pile = state.tableau[source.pileIndex]
    if (source.cardIndex >= pile.cards.length) return null
    const run = pile.cards.slice(source.cardIndex)
    if (!run[0].faceUp) return null   // Can't move face-down cards
    movingCards = run
    const remaining = pile.cards.slice(0, source.cardIndex)
    const updatedPile = remaining.length > 0 ? flipTopCard({ cards: remaining }) : { cards: [] }
    newSource = {
      ...state,
      tableau: setPile(state.tableau, source.pileIndex, updatedPile),
    }
  } else {
    // source.type === 'foundation' — only single-card moves back to tableau
    const fPile = state.foundations[source.pileIndex]
    if (fPile.cards.length === 0) return null
    const top = fPile.cards[fPile.cards.length - 1]
    movingCards = [top]
    newSource = {
      ...state,
      foundations: setPile(
        state.foundations,
        source.pileIndex,
        { cards: fPile.cards.slice(0, -1) },
      ),
    }
  }

  const cardToPlace = movingCards[0]

  // --- Apply to target ---
  if (target.type === 'foundation') {
    if (movingCards.length !== 1) return null   // Only single cards to foundation
    const fPile = newSource.foundations[target.pileIndex]
    if (!canPlaceOnFoundation(cardToPlace, fPile)) {
      return { ...state, errorCount: state.errorCount + 1 }
    }
    const newFoundations = setPile(
      newSource.foundations,
      target.pileIndex,
      { cards: [...fPile.cards, cardToPlace] },
    )
    const next = { ...newSource, foundations: newFoundations }
    return checkWin(next)
  }

  // target.type === 'tableau'
  const tPile = newSource.tableau[target.pileIndex]
  const topCard = tPile.cards.length > 0 ? tPile.cards[tPile.cards.length - 1] : null
  if (!canPlaceOnTableau(cardToPlace, topCard)) {
    return { ...state, errorCount: state.errorCount + 1 }
  }
  const newTableau = setPile(
    newSource.tableau,
    target.pileIndex,
    { cards: [...tPile.cards, ...movingCards] },
  )
  return { ...newSource, tableau: newTableau }
}

/**
 * Auto-move the top card of talon or a tableau column to a foundation
 * if legal. Returns null if no auto-move is available.
 */
export function autoMoveToFoundation(
  state: GameState,
  source: CardSource,
): GameState | null {
  let card: Card | null = null

  if (source.type === 'talon') {
    const talon = state.talon
    if (talon.cards.length === 0) return null
    card = talon.cards[talon.cards.length - 1]
  } else if (source.type === 'tableau') {
    const pile = state.tableau[source.pileIndex]
    if (pile.cards.length === 0) return null
    card = pile.cards[pile.cards.length - 1]
  } else {
    return null
  }

  const fIdx = foundationIndexForSuit(card.suit)
  const target: CardTarget = { type: 'foundation', pileIndex: fIdx }
  return applyMove(state, source, target)
}

// ---------------------------------------------------------------------------
// Win detection
// ---------------------------------------------------------------------------

function checkWin(state: GameState): GameState {
  const won = state.foundations.every(f => f.cards.length === 13)
  return { ...state, won }
}

// ---------------------------------------------------------------------------
// Serialization helpers (for save/restore — not used in M1 but useful for testing)
// ---------------------------------------------------------------------------

export function countFaceDownCards(state: GameState): number {
  return state.tableau.reduce(
    (acc, pile) => acc + pile.cards.filter(c => !c.faceUp).length,
    0,
  )
}

// ---------------------------------------------------------------------------
// Move metadata helpers — M1 v0.5 per-move telemetry
//
// @decision DEC-GAMES-006
// @title move_made event captured per move, not per drag
// @status accepted
// @rationale A drag that returns to origin still counts as a move attempt
//   for the invalid-click signal. One event per pointerdown/pointerup pair
//   matches the cognitive effort model better than only counting completed drops.
// ---------------------------------------------------------------------------

/**
 * MoveType string enum — matches the move_type field in game.move_made events.
 * Must stay in sync with the backend GameMoveMadeEvent.move_type comment.
 */
export type MoveType =
  | 'tableau-to-tableau'
  | 'tableau-to-foundation'
  | 'talon-to-tableau'
  | 'talon-to-foundation'
  | 'foundation-to-tableau'
  | 'stock-flip'
  | 'recycle'
  | 'invalid'

/**
 * Derive the move_type string from a source+target pair.
 *
 * drawFromStock uses 'stock-flip' when stock has cards, 'recycle' when empty.
 * Pass wasRecycle=true when the stock was empty before the draw call.
 * For applyMove calls, source and target fully determine the type.
 * For undo, pass source=null — the caller sets was_undo=true and move_type
 * can be derived post-hoc or left as 'invalid' since undo payloads are
 * informational only.
 */
export function getMoveType(
  source: CardSource | null,
  target: CardTarget | null,
  wasRecycle?: boolean,
): MoveType {
  if (source === null) {
    // undo — no meaningful source/target
    return 'invalid'
  }
  if (source.type === 'tableau' && target === null) {
    return wasRecycle ? 'recycle' : 'stock-flip'
  }
  if (source.type === 'talon' && target?.type === 'tableau') return 'talon-to-tableau'
  if (source.type === 'talon' && target?.type === 'foundation') return 'talon-to-foundation'
  if (source.type === 'tableau' && target?.type === 'tableau') return 'tableau-to-tableau'
  if (source.type === 'tableau' && target?.type === 'foundation') return 'tableau-to-foundation'
  if (source.type === 'foundation' && target?.type === 'tableau') return 'foundation-to-tableau'
  return 'invalid'
}

/**
 * Return the card value (1–52) of the card being moved, or null for
 * non-card moves (stock-flip, recycle).
 *
 * For tableau→* moves, the card at source.cardIndex is the moving card.
 * For talon→* moves, the top talon card is moving.
 * For stock-flip / recycle, there is no single "moving card" to report.
 */
export function getMovedCardValue(
  state: GameState,
  source: CardSource | null,
): number | null {
  if (source === null) return null
  if (source.type === 'talon') {
    const top = state.talon.cards[state.talon.cards.length - 1]
    return top ? top.value : null
  }
  if (source.type === 'tableau') {
    const pile = state.tableau[source.pileIndex]
    const card = pile?.cards[source.cardIndex]
    return card ? card.value : null
  }
  if (source.type === 'foundation') {
    const pile = state.foundations[source.pileIndex]
    const top = pile?.cards[pile.cards.length - 1]
    return top ? top.value : null
  }
  return null
}
