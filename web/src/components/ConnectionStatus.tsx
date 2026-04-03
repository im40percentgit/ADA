/**
 * ConnectionStatus — global WebSocket connection status banner
 *
 * Renders a fixed banner at the top of the viewport when the connection is
 * not fully open. Shows nothing when connected (open state). The three
 * visible states are:
 *
 *   connecting   — first load, no prior connection established
 *   reconnecting — connection dropped, retrying with backoff
 *   closed       — intentionally closed or permanently failed
 *
 * The banner is intentionally unobtrusive: it sits at the top of the page,
 * uses role="status" (live region, polite), and does not block interaction.
 * Screen readers announce status changes without interrupting the user.
 *
 * @decision DEC-FRONTEND-016
 * @title ConnectionStatus is a global banner, not per-component inline status
 * @status accepted
 * @rationale Multiple components (Chat, BoardView) share the same WebSocket.
 *   A single global banner avoids duplicate status UI and ensures consistent
 *   messaging. The banner is mounted at the App root so it covers all views.
 *   The component is intentionally thin — it owns no state, only receives
 *   the current status as a prop.
 */

import type { ReconnectingWsStatus } from '../hooks/useReconnectingWebSocket'

export interface ConnectionStatusProps {
  status: ReconnectingWsStatus
}

const STATUS_CONFIG: Record<
  Exclude<ReconnectingWsStatus, 'open'>,
  { label: string; modifier: string }
> = {
  connecting: {
    label: 'Connecting…',
    modifier: 'connecting',
  },
  reconnecting: {
    label: 'Reconnecting…',
    modifier: 'reconnecting',
  },
  closed: {
    label: 'Disconnected — reload to reconnect',
    modifier: 'closed',
  },
}

export function ConnectionStatus({ status }: ConnectionStatusProps) {
  // When connected, render nothing — no DOM noise in the happy path
  if (status === 'open') return null

  const config = STATUS_CONFIG[status]

  return (
    <div
      className={`connection-status connection-status--${config.modifier}`}
      role="status"
      aria-live="polite"
      aria-label={`Connection status: ${config.label}`}
    >
      <span className="connection-status__dot" aria-hidden="true" />
      <span className="connection-status__label">{config.label}</span>
    </div>
  )
}
