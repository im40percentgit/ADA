/**
 * SessionsCard — recent session summaries for the caregiver dashboard.
 *
 * Lists up to 5 recent sessions with SOAP plan highlights, key topics,
 * and risk flags. Shows "No sessions yet" when the list is empty.
 *
 * @decision DEC-FRONTEND-023
 * @title SessionsCard shows plan + topics + risk_flags, omits subjective/assessment
 * @status accepted
 * @rationale The SOAP summary has four fields: subjective (patient's own words),
 *   assessment (clinical interpretation), plan (next steps), key_topics, and
 *   risk_flags. Caregivers need actionable information: what happens next (plan),
 *   what was discussed (key_topics), and what to watch for (risk_flags).
 *   Subjective and assessment fields contain clinically sensitive language that
 *   is better reviewed in a full clinical context, not a caregiver summary card.
 */

import type { CaregiverSession } from '../types'

interface SessionsCardProps {
  sessions: CaregiverSession[]
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function SessionsCard({ sessions }: SessionsCardProps) {
  return (
    <section className="cg-card cg-sessions" aria-label="Recent sessions">
      <h2 className="cg-card__title">Recent Sessions</h2>

      {sessions.length === 0 ? (
        <p className="cg-card__empty">No sessions yet</p>
      ) : (
        <ul className="cg-sessions__list">
          {sessions.map((s) => (
            <li key={s.id} className="cg-sessions__item">
              <span className="cg-sessions__date">{formatDate(s.started_at)}</span>

              {s.summary ? (
                <>
                  {s.summary.plan && (
                    <div className="cg-sessions__section">
                      <span className="cg-sessions__label">Next Steps</span>
                      <p className="cg-sessions__text">{s.summary.plan}</p>
                    </div>
                  )}
                  {s.summary.key_topics.length > 0 && (
                    <div className="cg-sessions__section">
                      <span className="cg-sessions__label">Topics Discussed</span>
                      <div className="cg-sessions__tags">
                        {s.summary.key_topics.map((t, i) => (
                          <span key={i} className="cg-sessions__tag">{t}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {s.summary.risk_flags.length > 0 && (
                    <div className="cg-sessions__section cg-sessions__section--risk">
                      <span className="cg-sessions__label">Things to Watch</span>
                      <div className="cg-sessions__tags cg-sessions__tags--risk">
                        {s.summary.risk_flags.map((f, i) => (
                          <span key={i} className="cg-sessions__tag cg-sessions__tag--risk">{f}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <p className="cg-sessions__no-summary">Session in progress or summary pending</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
