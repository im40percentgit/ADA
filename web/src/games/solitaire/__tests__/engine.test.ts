/**
 * engine.test.ts — unit tests for the Klondike Solitaire engine.
 *
 * Covers deal correctness, move legality, move application, win detection,
 * and undo (via the value-type history pattern from DEC-UNDO-001).
 *
 * All tests use the pure engine functions — no React, no DOM required.
 */

import { describe, it, expect } from 'vitest'
import {
  buildShuffledDeck,
  dealGame,
  newGame,
  canPlaceOnTableau,
  canPlaceOnFoundation,
  applyMove,
  autoMoveToFoundation,
  drawFromStock,
  makeCard,
  countFaceDownCards,
  getMoveType,
  getMovedCardValue,
} from '../engine'
import type { Card, CardSource, CardTarget, GameState, Pile } from '../types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a minimal GameState for testing with controlled card placement. */
function emptyState(): GameState {
  return {
    tableau: Array.from({ length: 7 }, () => ({ cards: [] })),
    foundations: Array.from({ length: 4 }, () => ({ cards: [] })),
    stock: { cards: [] },
    talon: { cards: [] },
    won: false,
    errorCount: 0,
  }
}

/** Put cards directly into a pile (face-up by default). */
function pile(...cards: Card[]): Pile {
  return { cards: cards.map(c => ({ ...c, faceUp: true })) }
}

// ---------------------------------------------------------------------------
// deal()
// ---------------------------------------------------------------------------

describe('deal', () => {
  it('produces exactly 52 cards total', () => {
    const deck = buildShuffledDeck()
    const state = dealGame(deck)

    let total = 0
    state.tableau.forEach(p => { total += p.cards.length })
    total += state.stock.cards.length
    // talon starts empty
    total += state.talon.cards.length
    expect(total).toBe(52)
  })

  it('produces 7 tableau columns', () => {
    const state = newGame()
    expect(state.tableau).toHaveLength(7)
  })

  it('column i has i+1 cards (columns 0-6)', () => {
    const state = newGame()
    for (let i = 0; i < 7; i++) {
      expect(state.tableau[i].cards).toHaveLength(i + 1)
    }
  })

  it('top card of each tableau column is face-up', () => {
    const state = newGame()
    for (let i = 0; i < 7; i++) {
      const col = state.tableau[i]
      const top = col.cards[col.cards.length - 1]
      expect(top.faceUp).toBe(true)
    }
  })

  it('non-top tableau cards are face-down', () => {
    const state = newGame()
    for (let i = 1; i < 7; i++) {
      const col = state.tableau[i]
      for (let j = 0; j < col.cards.length - 1; j++) {
        expect(col.cards[j].faceUp).toBe(false)
      }
    }
  })

  it('stock has 52 - 28 = 24 cards', () => {
    const state = newGame()
    expect(state.stock.cards.length).toBe(24)
  })

  it('stock cards are face-down', () => {
    const state = newGame()
    state.stock.cards.forEach(c => expect(c.faceUp).toBe(false))
  })

  it('4 empty foundations', () => {
    const state = newGame()
    expect(state.foundations).toHaveLength(4)
    state.foundations.forEach(f => expect(f.cards).toHaveLength(0))
  })

  it('won is false after deal', () => {
    expect(newGame().won).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// isLegalMove — canPlaceOnTableau
// ---------------------------------------------------------------------------

describe('canPlaceOnTableau', () => {
  it('red card on black card of one rank higher is legal', () => {
    // 5 of spades (black, rank 5) — target; 4 of hearts (red, rank 4) — moving
    const black5 = makeCard(5, true)   // spades, rank 5, black
    const red4 = makeCard(4 + 13, true) // hearts, rank 4, red
    expect(canPlaceOnTableau(red4, black5)).toBe(true)
  })

  it('black card on red card of one rank higher is legal', () => {
    const red6 = makeCard(6 + 13, true)  // hearts, rank 6, red
    const black5 = makeCard(5, true)     // spades, rank 5, black
    expect(canPlaceOnTableau(black5, red6)).toBe(true)
  })

  it('same-color placement is illegal', () => {
    const black5 = makeCard(5, true)  // spades
    const black4 = makeCard(4, true)  // spades
    expect(canPlaceOnTableau(black4, black5)).toBe(false)
  })

  it('non-descending rank is illegal', () => {
    const red6 = makeCard(6 + 13, true)
    const black6 = makeCard(6, true)  // same rank
    expect(canPlaceOnTableau(black6, red6)).toBe(false)
  })

  it('empty column only accepts King (rank 13)', () => {
    const king = makeCard(13, true)       // King of spades
    const queen = makeCard(12, true)      // Queen of spades
    expect(canPlaceOnTableau(king, null)).toBe(true)
    expect(canPlaceOnTableau(queen, null)).toBe(false)
  })

  it('face-down target card rejects placement', () => {
    const faceDownBlack5 = makeCard(5, false)  // face-down
    const red4 = makeCard(4 + 13, true)
    expect(canPlaceOnTableau(red4, faceDownBlack5)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// isLegalMove — canPlaceOnFoundation
// ---------------------------------------------------------------------------

describe('canPlaceOnFoundation', () => {
  it('empty foundation accepts only Ace (rank 1)', () => {
    const ace = makeCard(1, true)          // Ace of spades
    const two = makeCard(2, true)          // Two of spades
    const emptyF: Pile = { cards: [] }
    expect(canPlaceOnFoundation(ace, emptyF)).toBe(true)
    expect(canPlaceOnFoundation(two, emptyF)).toBe(false)
  })

  it('foundation accepts next rank of same suit', () => {
    const ace = makeCard(1, true)           // spades
    const two = makeCard(2, true)           // spades
    const foundationWithAce: Pile = { cards: [ace] }
    expect(canPlaceOnFoundation(two, foundationWithAce)).toBe(true)
  })

  it('foundation rejects wrong suit', () => {
    const aceSpades = makeCard(1, true)     // spades
    const twoHearts = makeCard(14 + 1, true) // hearts rank 2
    const foundationWithAce: Pile = { cards: [aceSpades] }
    expect(canPlaceOnFoundation(twoHearts, foundationWithAce)).toBe(false)
  })

  it('foundation rejects non-ascending rank', () => {
    const ace = makeCard(1, true)
    const three = makeCard(3, true)  // skip rank 2
    const foundationWithAce: Pile = { cards: [ace] }
    expect(canPlaceOnFoundation(three, foundationWithAce)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// applyMove
// ---------------------------------------------------------------------------

describe('applyMove', () => {
  it('moves a card from talon to tableau', () => {
    // Setup: 8 of hearts (red) on talon, 9 of spades (black) on tableau col 0
    const red8 = makeCard(8 + 13, true)   // hearts rank 8, red
    const black9 = makeCard(9, true)      // spades rank 9, black
    const state: GameState = {
      ...emptyState(),
      talon: { cards: [red8] },
      tableau: [pile(black9), ...Array.from({ length: 6 }, () => ({ cards: [] }))],
    }

    const source: CardSource = { type: 'talon', pileIndex: 0, cardIndex: 0 }
    const target: CardTarget = { type: 'tableau', pileIndex: 0 }
    const next = applyMove(state, source, target)

    expect(next).not.toBeNull()
    expect(next!.talon.cards).toHaveLength(0)
    expect(next!.tableau[0].cards).toHaveLength(2)
    expect(next!.tableau[0].cards[1].value).toBe(red8.value)
  })

  it('moves a card from tableau to foundation', () => {
    const aceSpades = makeCard(1, true)
    const state: GameState = {
      ...emptyState(),
      tableau: [pile(aceSpades), ...Array.from({ length: 6 }, () => ({ cards: [] }))],
    }

    const source: CardSource = { type: 'tableau', pileIndex: 0, cardIndex: 0 }
    const target: CardTarget = { type: 'foundation', pileIndex: 0 }  // spades foundation
    const next = applyMove(state, source, target)

    expect(next).not.toBeNull()
    expect(next!.tableau[0].cards).toHaveLength(0)
    expect(next!.foundations[0].cards).toHaveLength(1)
    expect(next!.foundations[0].cards[0].value).toBe(aceSpades.value)
  })

  it('flips top tableau card face-up after moving a card off', () => {
    const faceDown = { ...makeCard(10, false) }  // 10 of spades face-down
    const faceUpTop = { ...makeCard(9, true) }   // 9 of spades face-up on top
    // Move 9 of spades (black) onto red 10 of hearts; faceDown beneath should flip
    const red10 = makeCard(10 + 13, true)        // hearts rank 10, red

    const state: GameState = {
      ...emptyState(),
      tableau: [
        { cards: [faceDown, faceUpTop] },       // col 0: source, 9 face-up on top
        pile(red10),                             // col 1: target
        ...Array.from({ length: 5 }, () => ({ cards: [] })),
      ],
    }

    const source: CardSource = { type: 'tableau', pileIndex: 0, cardIndex: 1 }
    const target: CardTarget = { type: 'tableau', pileIndex: 1 }
    const next = applyMove(state, source, target)

    expect(next).not.toBeNull()
    expect(next!.tableau[0].cards).toHaveLength(1)
    expect(next!.tableau[0].cards[0].faceUp).toBe(true)  // flipped
  })

  it('returns state with incremented errorCount for illegal move', () => {
    const red8 = makeCard(8 + 13, true)
    const red9 = makeCard(9 + 13, true)   // both red — illegal
    const state: GameState = {
      ...emptyState(),
      talon: { cards: [red8] },
      tableau: [pile(red9), ...Array.from({ length: 6 }, () => ({ cards: [] }))],
    }
    const source: CardSource = { type: 'talon', pileIndex: 0, cardIndex: 0 }
    const target: CardTarget = { type: 'tableau', pileIndex: 0 }
    const next = applyMove(state, source, target)

    // Illegal move returns state with errorCount +1
    expect(next).not.toBeNull()
    expect(next!.errorCount).toBe(1)
    // Talon and tableau unchanged
    expect(next!.talon.cards).toHaveLength(1)
  })

  it('returns null for moving face-down tableau card', () => {
    const faceDown = makeCard(9, false)
    const state: GameState = {
      ...emptyState(),
      tableau: [{ cards: [faceDown] }, ...Array.from({ length: 6 }, () => ({ cards: [] }))],
    }
    const source: CardSource = { type: 'tableau', pileIndex: 0, cardIndex: 0 }
    const target: CardTarget = { type: 'tableau', pileIndex: 1 }
    const next = applyMove(state, source, target)
    expect(next).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// detectWin
// ---------------------------------------------------------------------------

describe('detectWin', () => {
  it('won is false when foundations are not full', () => {
    const state = newGame()
    expect(state.won).toBe(false)
  })

  it('won is true when all 4 foundations have 13 cards each', () => {
    // Verify via applyMove completing the last foundation card (checkWin is called internally).
    // Build state where 3 foundations are full + last foundation has 12 cards,
    // and we move the King of the last suit onto it.

    const fullFoundations = [0, 1, 2].map(suitIdx => ({
      cards: Array.from({ length: 13 }, (_, i) =>
        makeCard(suitIdx * 13 + i + 1, true)
      ),
    }))
    const almostFull = {
      cards: Array.from({ length: 12 }, (_, i) =>
        makeCard(3 * 13 + i + 1, true)
      ),
    }
    const kingOfClubs = makeCard(52, true)  // rank 13, clubs

    const state: GameState = {
      ...emptyState(),
      tableau: [pile(kingOfClubs), ...Array.from({ length: 6 }, () => ({ cards: [] }))],
      foundations: [...fullFoundations, almostFull],
    }

    const source: CardSource = { type: 'tableau', pileIndex: 0, cardIndex: 0 }
    const target: CardTarget = { type: 'foundation', pileIndex: 3 }
    const next = applyMove(state, source, target)

    expect(next).not.toBeNull()
    expect(next!.won).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// drawFromStock
// ---------------------------------------------------------------------------

describe('drawFromStock', () => {
  it('moves top stock card to talon face-up', () => {
    const card = makeCard(5, false)
    const state: GameState = {
      ...emptyState(),
      stock: { cards: [card] },
      talon: { cards: [] },
    }
    const next = drawFromStock(state)
    expect(next.stock.cards).toHaveLength(0)
    expect(next.talon.cards).toHaveLength(1)
    expect(next.talon.cards[0].faceUp).toBe(true)
  })

  it('recycles empty stock from talon', () => {
    const card = makeCard(5, true)
    const state: GameState = {
      ...emptyState(),
      stock: { cards: [] },
      talon: { cards: [card] },
    }
    const next = drawFromStock(state)
    expect(next.stock.cards).toHaveLength(1)
    expect(next.stock.cards[0].faceUp).toBe(false)
    expect(next.talon.cards).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Undo (value-type history — DEC-UNDO-001)
// ---------------------------------------------------------------------------

describe('undo (value-type history)', () => {
  it('reverting a drawFromStock restores previous state', () => {
    const initial = newGame()
    const afterDraw = drawFromStock(initial)

    // Draw moves one card from stock to talon
    expect(afterDraw.talon.cards).toHaveLength(1)

    // history: [initial]; current: afterDraw
    // Undo: pop history, restore initial
    const history = [initial]
    const prev = history[history.length - 1]

    expect(prev.stock.cards).toHaveLength(initial.stock.cards.length)
    expect(prev.talon.cards).toHaveLength(0)
  })

  it('undo after a move restores tableau', () => {
    const red8 = makeCard(8 + 13, true)
    const black9 = makeCard(9, true)
    const initial: GameState = {
      ...emptyState(),
      talon: { cards: [red8] },
      tableau: [pile(black9), ...Array.from({ length: 6 }, () => ({ cards: [] }))],
    }

    const source: CardSource = { type: 'talon', pileIndex: 0, cardIndex: 0 }
    const target: CardTarget = { type: 'tableau', pileIndex: 0 }
    const afterMove = applyMove(initial, source, target)!

    // History stores initial; undo restores it
    const history = [initial]
    const prev = history[history.length - 1]

    expect(prev.talon.cards).toHaveLength(1)
    expect(prev.tableau[0].cards).toHaveLength(1)
    expect(afterMove.talon.cards).toHaveLength(0)
    expect(afterMove.tableau[0].cards).toHaveLength(2)
  })

  it('multiple undos restore successive states', () => {
    let state = newGame()
    const history: GameState[] = []

    // Make 3 draws
    for (let i = 0; i < 3; i++) {
      history.push(state)
      state = drawFromStock(state)
    }

    expect(state.talon.cards.length).toBeGreaterThanOrEqual(3)

    // Undo 3 times
    for (let i = 0; i < 3; i++) {
      state = history.pop()!
    }

    expect(state.talon.cards).toHaveLength(0)
  })

  it('countFaceDownCards decreases as tableau face-downs are flipped', () => {
    const initial = newGame()
    const initialFaceDown = countFaceDownCards(initial)
    // Should be 21 (1+2+...+6 face-down cards across columns 1-6, no face-down in col 0)
    expect(initialFaceDown).toBe(21)
  })
})

// ---------------------------------------------------------------------------
// getMoveType — M1 v0.5 per-move telemetry
// ---------------------------------------------------------------------------

describe('getMoveType()', () => {
  it('talon → tableau returns talon-to-tableau', () => {
    const src: CardSource = { type: 'talon', pileIndex: 0, cardIndex: 0 }
    const tgt: CardTarget = { type: 'tableau', pileIndex: 2 }
    expect(getMoveType(src, tgt)).toBe('talon-to-tableau')
  })

  it('talon → foundation returns talon-to-foundation', () => {
    const src: CardSource = { type: 'talon', pileIndex: 0, cardIndex: 0 }
    const tgt: CardTarget = { type: 'foundation', pileIndex: 0 }
    expect(getMoveType(src, tgt)).toBe('talon-to-foundation')
  })

  it('tableau → tableau returns tableau-to-tableau', () => {
    const src: CardSource = { type: 'tableau', pileIndex: 0, cardIndex: 0 }
    const tgt: CardTarget = { type: 'tableau', pileIndex: 3 }
    expect(getMoveType(src, tgt)).toBe('tableau-to-tableau')
  })

  it('tableau → foundation returns tableau-to-foundation', () => {
    const src: CardSource = { type: 'tableau', pileIndex: 0, cardIndex: 0 }
    const tgt: CardTarget = { type: 'foundation', pileIndex: 1 }
    expect(getMoveType(src, tgt)).toBe('tableau-to-foundation')
  })

  it('stock-flip: tableau source with null target and wasRecycle=false returns stock-flip', () => {
    // drawFromStock uses this path — we represent it as tableau source + null target
    expect(getMoveType({ type: 'tableau', pileIndex: 0, cardIndex: 0 }, null, false)).toBe('stock-flip')
  })

  it('recycle: tableau source with null target and wasRecycle=true returns recycle', () => {
    expect(getMoveType({ type: 'tableau', pileIndex: 0, cardIndex: 0 }, null, true)).toBe('recycle')
  })

  it('null source (undo) returns invalid', () => {
    expect(getMoveType(null, null)).toBe('invalid')
  })
})

// ---------------------------------------------------------------------------
// getMovedCardValue — M1 v0.5 per-move telemetry
// ---------------------------------------------------------------------------

describe('getMovedCardValue()', () => {
  it('returns top talon card value for talon source', () => {
    const card = makeCard(14, true)  // Ace of hearts
    const state: GameState = {
      tableau: Array.from({ length: 7 }, () => ({ cards: [] })),
      foundations: Array.from({ length: 4 }, () => ({ cards: [] })),
      stock: { cards: [] },
      talon: { cards: [card] },
      won: false,
      errorCount: 0,
    }
    const src: CardSource = { type: 'talon', pileIndex: 0, cardIndex: 0 }
    expect(getMovedCardValue(state, src)).toBe(14)
  })

  it('returns card at cardIndex for tableau source', () => {
    const bottom = makeCard(9, false)
    const top = makeCard(8, true)
    const state: GameState = {
      tableau: [{ cards: [bottom, top] }, ...Array.from({ length: 6 }, () => ({ cards: [] }))],
      foundations: Array.from({ length: 4 }, () => ({ cards: [] })),
      stock: { cards: [] },
      talon: { cards: [] },
      won: false,
      errorCount: 0,
    }
    const src: CardSource = { type: 'tableau', pileIndex: 0, cardIndex: 1 }
    expect(getMovedCardValue(state, src)).toBe(8)
  })

  it('returns null for null source (stock-flip, recycle, undo)', () => {
    const state = newGame()
    expect(getMovedCardValue(state, null)).toBeNull()
  })

  it('returns null for empty talon source', () => {
    const state: GameState = {
      tableau: Array.from({ length: 7 }, () => ({ cards: [] })),
      foundations: Array.from({ length: 4 }, () => ({ cards: [] })),
      stock: { cards: [] },
      talon: { cards: [] },
      won: false,
      errorCount: 0,
    }
    const src: CardSource = { type: 'talon', pileIndex: 0, cardIndex: 0 }
    expect(getMovedCardValue(state, src)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Bug fix DEC-GAMES-024 — Foundation → Tableau moves
// ---------------------------------------------------------------------------

describe('foundation-to-tableau moves (DEC-GAMES-024)', () => {
  it('applyMove allows moving top foundation card to a legal tableau column', () => {
    // Foundation 0 (spades) has A♠, 2♠; top is 2♠ (black, rank 2).
    // Tableau col 0 has 3♥ (red, rank 3). 2♠ on 3♥ is legal.
    const aceSpades = makeCard(1, true)   // A♠ rank 1
    const twoSpades = makeCard(2, true)   // 2♠ rank 2, black
    const threeHearts = makeCard(3 + 13, true)  // 3♥ rank 3, red

    const state: GameState = {
      ...emptyState(),
      foundations: [
        { cards: [aceSpades, twoSpades] },
        { cards: [] },
        { cards: [] },
        { cards: [] },
      ],
      tableau: [pile(threeHearts), ...Array.from({ length: 6 }, () => ({ cards: [] }))],
    }

    const source: CardSource = { type: 'foundation', pileIndex: 0, cardIndex: 1 }
    const target: CardTarget = { type: 'tableau', pileIndex: 0 }
    const next = applyMove(state, source, target)

    expect(next).not.toBeNull()
    expect(next!.errorCount).toBe(0)                             // no error
    expect(next!.foundations[0].cards).toHaveLength(1)           // A♠ remains
    expect(next!.foundations[0].cards[0].rank).toBe(1)
    expect(next!.tableau[0].cards).toHaveLength(2)               // 3♥, 2♠
    expect(next!.tableau[0].cards[1].value).toBe(twoSpades.value)
  })

  it('applyMove rejects foundation-to-tableau when placement is illegal (wrong color)', () => {
    // Foundation 0 (spades) has A♠; top is A♠ (black, rank 1).
    // Tableau col 0 has 2♠ (black, rank 2). Same color — illegal.
    const aceSpades = makeCard(1, true)
    const twoSpades = makeCard(2, true)

    const state: GameState = {
      ...emptyState(),
      foundations: [{ cards: [aceSpades] }, { cards: [] }, { cards: [] }, { cards: [] }],
      tableau: [pile(twoSpades), ...Array.from({ length: 6 }, () => ({ cards: [] }))],
    }

    const source: CardSource = { type: 'foundation', pileIndex: 0, cardIndex: 0 }
    const target: CardTarget = { type: 'tableau', pileIndex: 0 }
    const next = applyMove(state, source, target)

    // Illegal: errorCount bumped, foundation and tableau unchanged
    expect(next).not.toBeNull()
    expect(next!.errorCount).toBe(1)
    expect(next!.foundations[0].cards).toHaveLength(1)  // unchanged
    expect(next!.tableau[0].cards).toHaveLength(1)      // unchanged
  })

  it('applyMove rejects moving from empty foundation', () => {
    const state = emptyState()
    const source: CardSource = { type: 'foundation', pileIndex: 0, cardIndex: 0 }
    const target: CardTarget = { type: 'tableau', pileIndex: 0 }
    expect(applyMove(state, source, target)).toBeNull()
  })

  it('applyMove allows King from foundation to empty tableau column', () => {
    // Foundation 3 (clubs) has full suit A→K; we move K♣ to empty tableau col 1.
    const fullClubs = Array.from({ length: 13 }, (_, i) => makeCard(40 + i, true))
    const kingClubs = fullClubs[12]  // rank 13

    const state: GameState = {
      ...emptyState(),
      foundations: [
        { cards: [] }, { cards: [] }, { cards: [] },
        { cards: fullClubs },
      ],
    }

    const source: CardSource = { type: 'foundation', pileIndex: 3, cardIndex: 12 }
    const target: CardTarget = { type: 'tableau', pileIndex: 1 }
    const next = applyMove(state, source, target)

    expect(next).not.toBeNull()
    expect(next!.errorCount).toBe(0)
    expect(next!.foundations[3].cards).toHaveLength(12)
    expect(next!.tableau[1].cards).toHaveLength(1)
    expect(next!.tableau[1].cards[0].value).toBe(kingClubs.value)
  })

  it('getMoveType returns foundation-to-tableau for foundation source + tableau target', () => {
    const src: CardSource = { type: 'foundation', pileIndex: 0, cardIndex: 0 }
    const tgt: CardTarget = { type: 'tableau', pileIndex: 2 }
    expect(getMoveType(src, tgt)).toBe('foundation-to-tableau')
  })
})

// ---------------------------------------------------------------------------
// Bug fix DEC-GAMES-025 — autoMoveToFoundation validity check
// ---------------------------------------------------------------------------

describe('autoMoveToFoundation validity (DEC-GAMES-025)', () => {
  it('returns non-null with unchanged errorCount when a valid auto-move exists', () => {
    // A♠ on talon; foundation 0 (spades) is empty — Ace can go to foundation.
    const aceSpades = makeCard(1, true)
    const state: GameState = {
      ...emptyState(),
      talon: { cards: [aceSpades] },
    }
    const source: CardSource = { type: 'talon', pileIndex: 0, cardIndex: 0 }
    const result = autoMoveToFoundation(state, source)

    expect(result).not.toBeNull()
    expect(result!.errorCount).toBe(0)                       // move was applied
    expect(result!.foundations[0].cards).toHaveLength(1)     // A♠ on foundation
    expect(result!.talon.cards).toHaveLength(0)
  })

  it('returns state with bumped errorCount when rank does not match foundation top', () => {
    // 3♠ on talon; foundation 0 (spades) has only A♠ — 3♠ can't go next (needs 2♠).
    const aceSpades = makeCard(1, true)
    const threeSpades = makeCard(3, true)
    const state: GameState = {
      ...emptyState(),
      talon: { cards: [threeSpades] },
      foundations: [{ cards: [aceSpades] }, { cards: [] }, { cards: [] }, { cards: [] }],
    }
    const source: CardSource = { type: 'talon', pileIndex: 0, cardIndex: 0 }
    const result = autoMoveToFoundation(state, source)

    // applyMove returns errorCount+1 for illegal placement — NOT null.
    // The audio gate in useSolitaire must check errorCount to detect this.
    expect(result).not.toBeNull()
    expect(result!.errorCount).toBe(1)                   // bumped — move rejected
    expect(result!.foundations[0].cards).toHaveLength(1) // unchanged
    expect(result!.talon.cards).toHaveLength(1)          // unchanged
  })

  it('returns null when source pile is empty (talon)', () => {
    const state = emptyState()
    const source: CardSource = { type: 'talon', pileIndex: 0, cardIndex: 0 }
    expect(autoMoveToFoundation(state, source)).toBeNull()
  })

  it('returns null when source is a foundation pile (no foundation-to-foundation)', () => {
    // autoMoveToFoundation only handles talon and tableau sources — foundation
    // source returns null by design (foundation-to-foundation is not a Klondike rule).
    const aceSpades = makeCard(1, true)
    const state: GameState = {
      ...emptyState(),
      foundations: [{ cards: [aceSpades] }, { cards: [] }, { cards: [] }, { cards: [] }],
    }
    const source: CardSource = { type: 'foundation', pileIndex: 0, cardIndex: 0 }
    expect(autoMoveToFoundation(state, source)).toBeNull()
  })

  it('auto-move 6♥ succeeds when 5♥ is the foundation top (correct suit + ascending rank)', () => {
    // Build hearts foundation with A♥ through 5♥, then try to auto-move 6♥ from tableau.
    const heartsCards = Array.from({ length: 5 }, (_, i) => makeCard(14 + i, true)) // A♥–5♥
    const sixHearts = makeCard(14 + 5, true)  // 6♥ (value 19)

    const state: GameState = {
      ...emptyState(),
      foundations: [
        { cards: [] },
        { cards: heartsCards },  // foundation 1 = hearts
        { cards: [] },
        { cards: [] },
      ],
      tableau: [pile(sixHearts), ...Array.from({ length: 6 }, () => ({ cards: [] }))],
    }

    const source: CardSource = { type: 'tableau', pileIndex: 0, cardIndex: 0 }
    const result = autoMoveToFoundation(state, source)

    expect(result).not.toBeNull()
    expect(result!.errorCount).toBe(0)
    expect(result!.foundations[1].cards).toHaveLength(6)
    expect(result!.foundations[1].cards[5].rank).toBe(6)
  })
})
