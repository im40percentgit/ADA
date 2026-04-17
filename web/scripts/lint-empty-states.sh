#!/usr/bin/env bash
# @decision DEC-LINT-001
# @title Empty-State and Copy Lint Guard
# @status accepted
# @rationale Prevents regression of forbidden UI patterns that were replaced during
#            Phase 13e copy voice pass. Runs as part of CI and the `lint:empty-states`
#            npm script. Any match outside exempted directories exits 1 with a clear
#            diagnostic. Add `// lint-empty-states:allow` on the same line to suppress
#            a specific occurrence intentionally.
#
# Forbidden patterns (in .tsx files outside components/ui/ and test files):
#   1. 'Loading...' or 'Loading…' as string literals / JSX text
#   2. style={errorStyle} inline object references
#   3. browser alert() calls
#   4. Inline empty-state raw strings: 'No X yet', 'No X yet' (double-quoted)
#
# Exit codes:
#   0 — no violations found (clean)
#   1 — one or more violations found (lists each with file:line)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "${SCRIPT_DIR}/../src" && pwd)"

PASS=0
FAIL=1

# Colour helpers (degrade gracefully in CI)
RED=""
YELLOW=""
RESET=""
if [ -t 1 ]; then
  RED="\033[0;31m"
  YELLOW="\033[0;33m"
  RESET="\033[0m"
fi

violations=()

# ── helper ───────────────────────────────────────────────────────────────────
# check_pattern LABEL PATTERN [EXTRA_EXCLUDE...]
#   Greps SRC_DIR for PATTERN in .tsx files, skipping:
#     - components/ui/ (design-system primitives own their own text)
#     - *.test.tsx / *.spec.tsx (tests may assert on legacy strings)
#     - lines containing // lint-empty-states:allow
#   Any remaining matches are appended to $violations.
check_pattern() {
  local label="$1"
  local pattern="$2"
  shift 2
  local extra_excludes=("$@")

  # Build grep exclude-dir and exclude-file args
  local grep_args=(
    --recursive
    --include="*.tsx"
    --exclude-dir="ui"
    --line-number
    -E
  )

  local raw
  raw=$(grep "${grep_args[@]}" -- "$pattern" "$SRC_DIR" 2>/dev/null || true)

  # Filter out test files, comment-only lines, and suppressed lines.
  # Excludes:
  #   - *.test.tsx and *.spec.tsx
  #   - lines whose content (after "file:lineno:") begins with whitespace + // (single-line comment)
  #   - lines whose content begins with whitespace + * (JSDoc / block-comment continuation)
  #   - lines containing the suppression marker
  local filtered
  filtered=$(
    echo "$raw" \
      | grep -v '\.test\.tsx:' \
      | grep -v '\.spec\.tsx:' \
      | grep -v 'lint-empty-states:allow' \
      | grep -Pv ':\s*(//|\*)' \
      || true
  )

  # Apply any extra caller-supplied exclusions
  for excl in "${extra_excludes[@]}"; do
    filtered=$(echo "$filtered" | grep -v "$excl" || true)
  done

  if [ -n "$filtered" ]; then
    while IFS= read -r line; do
      [ -n "$line" ] && violations+=("${label}: ${line}")
    done <<< "$filtered"
  fi
}

# ── pattern 1: Loading string literals ───────────────────────────────────────
# Match 'Loading...' or 'Loading…' as quoted strings or bare JSX text.
# JSDoc comments are excluded via the comment-line filter below.
check_pattern \
  "Loading-literal" \
  "(>Loading\.\.\.<|>Loading…<|['\"]Loading\.\.\.['\"]|['\"]Loading…['\"])"

# ── pattern 2: inline errorStyle ─────────────────────────────────────────────
check_pattern \
  "inline-errorStyle" \
  "style=\{errorStyle\}"

# ── pattern 3: browser alert() ───────────────────────────────────────────────
# Match alert( that is not inside a comment.
check_pattern \
  "browser-alert" \
  "[^a-zA-Z0-9_]alert\s*\("

# ── pattern 4: inline empty-state raw strings ────────────────────────────────
# These are the pre-Phase-13e patterns: bare string literals passed as children
# or returned directly. The correct form is <EmptyState title="…"> (a prop, fine).
# We flag only the old patterns that appeared as raw JSX children / returned text:
#   >No sessions yet<   >No items yet<   >No notes yet<   >No boards yet<
check_pattern \
  "inline-empty-string" \
  ">(No sessions yet|No items yet|No notes yet|No boards yet)<"

# ── report ────────────────────────────────────────────────────────────────────
if [ ${#violations[@]} -eq 0 ]; then
  echo "lint-empty-states: PASS — no forbidden patterns found."
  exit $PASS
fi

echo ""
echo -e "${RED}lint-empty-states: FAIL — ${#violations[@]} violation(s) found${RESET}"
echo ""
for v in "${violations[@]}"; do
  echo -e "  ${YELLOW}${v}${RESET}"
done
echo ""
echo "To suppress a specific line intentionally, add:"
echo "  // lint-empty-states:allow"
echo "at the end of that line."
echo ""
exit $FAIL
