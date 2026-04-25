/**
 * SolitairePage — Klondike Solitaire game page for Ada patient UI.
 *
 * Renders the full board: 7 tableau columns, 4 foundations, stock, and talon.
 * Drag-and-drop uses Pointer Events with setPointerCapture for mouse + touch.
 * Deck style (corgi / classic) is persisted to localStorage.
 *
 * Session lifecycle: startSession() on mount, endSession('quit') on unmount.
 * visibilitychange and idle handling are owned by telemetry.ts — no duplication here.
 *
 * @decision DEC-GAMES-001
 * @title Native React component — game renders directly in Ada component tree
 * @status accepted
 * @rationale Iframe + postMessage bridge was rejected. See CHOICE.md and engine.ts.
 *
 * @decision DEC-GAMES-002
 * @title Pointer Events API for drag — onPointerDown/Move/Up + setPointerCapture
 * @status accepted
 * @rationale Single unified API for mouse and touch. No new npm dependencies.
 *   touch-action: none in CSS prevents browser scroll interference on mobile.
 *   setPointerCapture keeps events flowing to the source element during fast drags.
 *
 * @decision DEC-GAMES-009
 * @title Corgi photos are card backs only, never face-up art
 * @status accepted
 * @rationale Face-up cards always show standard playing-card art regardless of
 *   deckStyle. Corgi/Classic toggle only affects face-DOWN cards. Matches the
 *   original SwiftSolitaire CardBackManager behavior and preserves playability.
 *
 * @decision DEC-GAMES-011
 * @title Card sizing unified across both deck modes
 * @status accepted
 * @rationale Dogfood feedback: Classic mode rendered smaller than Corgi mode.
 *   Both modes now use the same card dimensions via shared CSS classes.
 */

import { useEffect, useRef, useCallback, useState } from 'react'
import { useSolitaire } from './useSolitaire'
import { corgiImagePath, classicBackPath, classicImagePath } from './engine'
import { startSession, endSession, resetIdle } from './telemetry'
import { getMuted, setMuted } from './audio'
import type { Card, CardSource, CardTarget, DeckStyle } from './types'
import './SolitairePage.css'

const DECK_LS_KEY = 'ada.solitaire.deck'

function readPersistedDeck(): DeckStyle {
  try {
    const v = localStorage.getItem(DECK_LS_KEY)
    if (v === 'corgi' || v === 'classic') return v
  } catch {
    // localStorage unavailable
  }
  return 'corgi'
}

// ---------------------------------------------------------------------------
// Sub-components: CardFace (face-up) and CardBack (face-down)
// ---------------------------------------------------------------------------

/**
 * CardFace — renders face-up card art.
 *
 * Always uses standard playing-card art regardless of deckStyle. When an image
 * asset exists (Ace, 2, J, Q, K) it renders a PNG; for ranks 3–10 (no image
 * in the Swift asset set) it falls back to a styled CSS text face that clearly
 * shows rank and suit symbol.
 *
 * deckStyle is intentionally NOT a prop here — faces are always standard art.
 */
interface CardFaceProps {
  card: Card
}

function CardFace({ card }: CardFaceProps) {
  const imgSrc = classicImagePath(card)
  const rankName =
    card.rank === 1  ? 'A' :
    card.rank === 11 ? 'J' :
    card.rank === 12 ? 'Q' :
    card.rank === 13 ? 'K' :
    String(card.rank)
  const suitSymbol =
    card.suit === 'spades'   ? '♠' :
    card.suit === 'hearts'   ? '♥' :
    card.suit === 'diamonds' ? '♦' : '♣'
  const colorClass = card.color === 'red' ? 'solitaire-card__classic--red' : 'solitaire-card__classic--black'

  return (
    <div className={`solitaire-card__face ${colorClass}`}>
      {/* Corner indicator — always present, top-left */}
      <span className="solitaire-card__corner">
        <span className="solitaire-card__rank">{rankName}</span>
        <span className="solitaire-card__suit">{suitSymbol}</span>
      </span>
      {/* Center decoration — image for A/2/J/Q/K, large suit symbol for 3-10 */}
      {imgSrc !== null ? (
        <img
          src={imgSrc}
          alt={`${rankName} of ${card.suit}`}
          className="solitaire-card__image solitaire-card__image--face"
          draggable={false}
        />
      ) : (
        <span className="solitaire-card__center-suit">{suitSymbol}</span>
      )}
    </div>
  )
}

/**
 * CardBack — renders face-down card art.
 *
 * In corgi mode: renders the corgi JPG assigned to this card's value.
 * In classic mode: renders the shared PlayingCard-back.png.
 *
 * @decision DEC-GAMES-009
 */
interface CardBackProps {
  card: Card
  deckStyle: DeckStyle
}

function CardBack({ card, deckStyle }: CardBackProps) {
  const src = deckStyle === 'corgi' ? corgiImagePath(card.value) : classicBackPath()
  const alt = deckStyle === 'corgi' ? 'Corgi card back' : 'Classic card back'
  return (
    <img
      src={src}
      alt={alt}
      className="solitaire-card__image"
      draggable={false}
    />
  )
}

// ---------------------------------------------------------------------------
// Drag state (ref-based, not React state — avoids re-renders during drag)
// ---------------------------------------------------------------------------

interface DragState {
  source: CardSource
  cards: Card[]
  // Ghost element position
  ghostX: number
  ghostY: number
  // Offset from pointer to top-left of first card
  offsetX: number
  offsetY: number
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

interface SolitairePageProps {
  onBack: () => void
}

export function SolitairePage({ onBack }: SolitairePageProps) {
  const initialDeck = readPersistedDeck()
  const { game, canUndo, deckStyle, completedHands, deal, draw, move, autoMove, undo, setDeckStyle } = useSolitaire(initialDeck)
  const dragRef = useRef<DragState | null>(null)
  const ghostRef = useRef<HTMLDivElement | null>(null)
  const boardRef = useRef<HTMLDivElement | null>(null)

  // Mute toggle: React state mirrors audio module state so the button re-renders.
  // getMuted() reads from localStorage on first call (lazy init).
  const [muted, setMutedState] = useState<boolean>(() => getMuted())

  // -------------------------------------------------------------------------
  // Session lifecycle
  // -------------------------------------------------------------------------

  useEffect(() => {
    void startSession(deckStyle)
    return () => {
      void endSession('quit')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Persist deck style choice
  useEffect(() => {
    try {
      localStorage.setItem(DECK_LS_KEY, deckStyle)
    } catch {
      // Ignore
    }
  }, [deckStyle])

  // Win detection — call recordHandCompleted is handled by useSolitaire internally
  // via completedHands, so we just observe won state here for banner.

  // -------------------------------------------------------------------------
  // Drag helpers
  // -------------------------------------------------------------------------

  const updateGhostPosition = useCallback((x: number, y: number) => {
    const ghost = ghostRef.current
    if (!ghost) return
    const ds = dragRef.current
    if (!ds) return
    ghost.style.left = `${x - ds.offsetX}px`
    ghost.style.top = `${y - ds.offsetY}px`
    ghost.style.display = 'flex'
  }, [])

  const clearGhost = useCallback(() => {
    const ghost = ghostRef.current
    if (ghost) {
      ghost.style.display = 'none'
      // Clear ghost children
      while (ghost.firstChild) ghost.removeChild(ghost.firstChild)
    }
    dragRef.current = null
  }, [])

  // Find which pile is under a pointer coordinate by walking DOM elements
  const findDropTarget = useCallback((x: number, y: number): CardTarget | null => {
    const board = boardRef.current
    if (!board) return null

    // Temporarily hide ghost so elementsFromPoint doesn't hit it
    const ghost = ghostRef.current
    const wasVisible = ghost?.style.display !== 'none'
    if (ghost && wasVisible) ghost.style.display = 'none'

    const elements = document.elementsFromPoint(x, y)

    if (ghost && wasVisible) ghost.style.display = 'flex'

    for (const el of elements) {
      const target = (el as HTMLElement).dataset?.dropTarget
      if (target) {
        const [type, idx] = target.split(':')
        if ((type === 'tableau' || type === 'foundation') && idx !== undefined) {
          return { type: type as 'tableau' | 'foundation', pileIndex: parseInt(idx, 10) }
        }
      }
    }
    return null
  }, [])

  // -------------------------------------------------------------------------
  // Pointer event handlers
  // -------------------------------------------------------------------------

  const handleCardPointerDown = useCallback((
    e: React.PointerEvent<HTMLDivElement>,
    source: CardSource,
    cards: Card[],
  ) => {
    if (cards.length === 0 || !cards[0].faceUp) return
    e.currentTarget.setPointerCapture(e.pointerId)
    e.stopPropagation()

    const rect = e.currentTarget.getBoundingClientRect()
    const ds: DragState = {
      source,
      cards,
      ghostX: e.clientX,
      ghostY: e.clientY,
      offsetX: e.clientX - rect.left,
      offsetY: e.clientY - rect.top,
    }
    dragRef.current = ds
    resetIdle()

    // Populate ghost element — always use standard face art (image or CSS text)
    const ghost = ghostRef.current
    if (ghost) {
      while (ghost.firstChild) ghost.removeChild(ghost.firstChild)
      const cardWidth = rect.width
      cards.forEach((card) => {
        const div = document.createElement('div')
        div.className = 'solitaire-card'
        div.style.width = `${cardWidth}px`

        // Face-up drag ghost: same structure as CardFace — corner + center decoration
        const rankName =
          card.rank === 1  ? 'A' :
          card.rank === 11 ? 'J' :
          card.rank === 12 ? 'Q' :
          card.rank === 13 ? 'K' :
          String(card.rank)
        const suitSymbol =
          card.suit === 'spades'   ? '♠' :
          card.suit === 'hearts'   ? '♥' :
          card.suit === 'diamonds' ? '♦' : '♣'
        const colorClass = card.color === 'red'
          ? 'solitaire-card__classic--red'
          : 'solitaire-card__classic--black'

        const face = document.createElement('div')
        face.className = `solitaire-card__face ${colorClass}`

        // Corner indicator
        const corner = document.createElement('span')
        corner.className = 'solitaire-card__corner'
        const rankSpan = document.createElement('span')
        rankSpan.className = 'solitaire-card__rank'
        rankSpan.textContent = rankName
        const suitSpan = document.createElement('span')
        suitSpan.className = 'solitaire-card__suit'
        suitSpan.textContent = suitSymbol
        corner.appendChild(rankSpan)
        corner.appendChild(suitSpan)
        face.appendChild(corner)

        // Center decoration
        const imgSrc = classicImagePath(card)
        if (imgSrc !== null) {
          const img = document.createElement('img')
          img.src = imgSrc
          img.alt = `${rankName} of ${card.suit}`
          img.className = 'solitaire-card__image solitaire-card__image--face'
          img.draggable = false
          face.appendChild(img)
        } else {
          const centerSuit = document.createElement('span')
          centerSuit.className = 'solitaire-card__center-suit'
          centerSuit.textContent = suitSymbol
          face.appendChild(centerSuit)
        }

        div.appendChild(face)
        ghost.appendChild(div)
      })
      updateGhostPosition(e.clientX, e.clientY)
    }
  }, [deckStyle, updateGhostPosition])

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return
    updateGhostPosition(e.clientX, e.clientY)
  }, [updateGhostPosition])

  const handlePointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const ds = dragRef.current
    if (!ds) return

    const target = findDropTarget(e.clientX, e.clientY)
    clearGhost()

    if (target) {
      move(ds.source, target)
    }
    resetIdle()
  }, [findDropTarget, clearGhost, move])

  // Double-click: auto-move to foundation
  const handleCardDoubleClick = useCallback((source: CardSource) => {
    autoMove(source)
    resetIdle()
  }, [autoMove])

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  function renderCard(
    card: Card,
    source: CardSource,
    cardIndex: number,
    isTopOfPile: boolean,
  ) {
    if (!card.faceUp) {
      return (
        <div
          key={`${source.type}-${source.pileIndex}-${cardIndex}`}
          className="solitaire-card"
          aria-label="Face-down card"
        >
          <CardBack card={card} deckStyle={deckStyle} />
        </div>
      )
    }

    const run = source.type === 'tableau'
      ? game.tableau[source.pileIndex].cards.slice(cardIndex)
      : [card]

    const sourceForDrag: CardSource = { ...source, cardIndex }

    return (
      <div
        key={`${source.type}-${source.pileIndex}-${card.value}`}
        className="solitaire-card"
        aria-label={`${card.rank} of ${card.suit}`}
        onPointerDown={(e) => handleCardPointerDown(e, sourceForDrag, run)}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onDoubleClick={isTopOfPile ? () => handleCardDoubleClick(sourceForDrag) : undefined}
      >
        <CardFace card={card} />
      </div>
    )
  }

  function renderTableauColumn(colIndex: number) {
    const pile = game.tableau[colIndex]
    const isEmpty = pile.cards.length === 0

    return (
      <div
        key={colIndex}
        className="solitaire-column"
        data-drop-target={`tableau:${colIndex}`}
      >
        {isEmpty ? (
          <div
            className="solitaire-pile-slot"
            data-drop-target={`tableau:${colIndex}`}
            aria-label={`Empty tableau column ${colIndex + 1}`}
          >
            K
          </div>
        ) : (
          pile.cards.map((card, idx) =>
            renderCard(
              card,
              { type: 'tableau', pileIndex: colIndex, cardIndex: idx },
              idx,
              idx === pile.cards.length - 1,
            )
          )
        )}
      </div>
    )
  }

  function renderFoundation(fIdx: number) {
    const pile = game.foundations[fIdx]
    const top = pile.cards.length > 0 ? pile.cards[pile.cards.length - 1] : null
    const suitSymbols = ['♠', '♥', '♦', '♣']

    if (!top) {
      return (
        <div
          key={fIdx}
          className="solitaire-pile-slot"
          data-drop-target={`foundation:${fIdx}`}
          aria-label={`Foundation ${fIdx + 1} — empty`}
        >
          {suitSymbols[fIdx]}
        </div>
      )
    }

    return (
      <div
        key={fIdx}
        className="solitaire-card"
        data-drop-target={`foundation:${fIdx}`}
        aria-label={`Foundation ${fIdx + 1} — ${top.rank} of ${top.suit}`}
        onDoubleClick={() => handleCardDoubleClick({ type: 'foundation', pileIndex: fIdx, cardIndex: pile.cards.length - 1 })}
      >
        <CardFace card={top} />
      </div>
    )
  }

  function renderStock() {
    const isEmpty = game.stock.cards.length === 0
    // Stock pile face-down card: use a placeholder CardBack using value=1 (back image
    // is the same for all cards in the same deck mode — value is only used for corgi
    // per-card mapping, but stock shows just the back so any value is fine here).
    const stockPlaceholderCard = game.stock.cards.length > 0
      ? game.stock.cards[game.stock.cards.length - 1]
      : null
    return (
      <div
        className={`solitaire-card solitaire-stock ${isEmpty ? 'solitaire-stock--empty solitaire-pile-slot' : ''}`}
        onClick={() => { draw(); resetIdle() }}
        aria-label={isEmpty ? 'Stock empty — click to recycle' : `Stock (${game.stock.cards.length} cards)`}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter') { draw(); resetIdle() } }}
      >
        {isEmpty ? (
          <span>↺</span>
        ) : stockPlaceholderCard ? (
          <CardBack card={stockPlaceholderCard} deckStyle={deckStyle} />
        ) : null}
      </div>
    )
  }

  function renderTalon() {
    const top = game.talon.cards.length > 0 ? game.talon.cards[game.talon.cards.length - 1] : null

    if (!top) {
      return (
        <div
          className="solitaire-pile-slot"
          aria-label="Talon empty"
        >
          ·
        </div>
      )
    }

    const source: CardSource = { type: 'talon', pileIndex: 0, cardIndex: game.talon.cards.length - 1 }

    return (
      <div
        className="solitaire-card"
        aria-label={`Talon — ${top.rank} of ${top.suit}`}
        onPointerDown={(e) => handleCardPointerDown(e, source, [top])}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onDoubleClick={() => handleCardDoubleClick(source)}
      >
        <CardFace card={top} />
      </div>
    )
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="solitaire-page">
      {/* Header */}
      <div className="solitaire-header">
        <button
          className="solitaire-header__back"
          onClick={onBack}
          aria-label="Back to dashboard"
        >
          ← Back
        </button>

        <span className="solitaire-header__title">Solitaire</span>

        <div className="solitaire-header__actions">
          {/* Sound mute toggle */}
          <button
            className="solitaire-header__btn solitaire-header__btn--icon"
            onClick={() => {
              const next = !muted
              setMuted(next)
              setMutedState(next)
            }}
            aria-label={muted ? 'Unmute sound effects' : 'Mute sound effects'}
            aria-pressed={muted}
            title={muted ? 'Sound off — click to enable' : 'Sound on — click to mute'}
          >
            {muted ? '🔇' : '🔊'}
          </button>

          {/* Deck back toggle — faces are always standard art; this controls backs only */}
          <div className="solitaire-header__deck-toggle" role="group" aria-label="Card back style">
            <button
              className={`solitaire-header__deck-btn${deckStyle === 'corgi' ? ' solitaire-header__deck-btn--active' : ''}`}
              onClick={() => setDeckStyle('corgi')}
              aria-pressed={deckStyle === 'corgi'}
            >
              Corgi backs
            </button>
            <button
              className={`solitaire-header__deck-btn${deckStyle === 'classic' ? ' solitaire-header__deck-btn--active' : ''}`}
              onClick={() => setDeckStyle('classic')}
              aria-pressed={deckStyle === 'classic'}
            >
              Classic backs
            </button>
          </div>

          <button
            className="solitaire-header__btn"
            onClick={undo}
            disabled={!canUndo}
            aria-label="Undo last move"
          >
            Undo
          </button>

          <button
            className="solitaire-header__btn"
            onClick={deal}
            aria-label="New game"
          >
            New
          </button>
        </div>
      </div>

      {/* Win banner */}
      {game.won && (
        <div className="solitaire-win-banner" role="status" aria-live="polite">
          You won! {completedHands > 1 ? `(${completedHands} hands this session)` : ''} — Play again?
        </div>
      )}

      {/* Board */}
      <div
        className="solitaire-board"
        ref={boardRef}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        {/* Top row: stock | talon | spacer | foundations (4) */}
        <div className="solitaire-top-row">
          {renderStock()}
          {renderTalon()}
          {/* Spacer */}
          <div aria-hidden="true" />
          {[0, 1, 2, 3].map(renderFoundation)}
        </div>

        {/* Tableau */}
        <div className="solitaire-tableau">
          {[0, 1, 2, 3, 4, 5, 6].map(renderTableauColumn)}
        </div>
      </div>

      {/* Drag ghost — absolutely positioned, pointer-events: none */}
      <div
        ref={ghostRef}
        className="solitaire-drag-ghost"
        style={{ display: 'none' }}
        aria-hidden="true"
      />
    </div>
  )
}
