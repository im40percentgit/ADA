# Corgi Card Mapping

52 unique JPG photos of the patient's late corgi, one per card face.

## Value → File Formula

```
fileIndex = (cardValue % 52) + 1
filename  = `corgi-${String(fileIndex).padStart(2, '0')}.jpg`
```

Where `cardValue` is 1–52, assigned by suit × rank:

| Suit    | Values  | Example             |
|---------|---------|---------------------|
| Spades  | 1–13    | A♠=1, 2♠=2, K♠=13  |
| Hearts  | 14–26   | A♥=14, 2♥=15, K♥=26 |
| Diamonds| 27–39   | A♦=27, 2♦=28, K♦=39 |
| Clubs   | 40–52   | A♣=40, 2♣=41, K♣=52 |

## Resulting File Range

- `corgi-01.jpg` → card value 1 (A♠) and 53 mod 52 = 1 (wraps, but max is 52)
- `corgi-52.jpg` → card value 52 (K♣)

All 52 files (`corgi-01.jpg` through `corgi-52.jpg`) are present in
`/games/solitaire/corgi/` (copied from
`/home/j/CerebrumCraft/solitaire/SwiftSolitaire/Solitaire/images/corgi/`).

## Canonical Source

`/home/j/CerebrumCraft/solitaire/SwiftSolitaire/Solitaire/images/corgi/` — the
original Swift project's asset bundle. Do NOT use the loose
`/home/j/CerebrumCraft/solitaire/corgi/` directory (incomplete, different files).
