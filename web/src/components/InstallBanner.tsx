/**
 * InstallBanner — PWA install prompt banner.
 *
 * Captures the browser's `beforeinstallprompt` event and presents a
 * dismissible banner inviting the user to install Ada as a home-screen app.
 * Pressing "Install" triggers the native install dialog. Pressing "Dismiss"
 * hides the banner for the current browser session and records the dismissal
 * in localStorage so it is not shown again across page reloads.
 *
 * The banner is suppressed entirely when:
 *   - The app is already running in standalone mode (already installed)
 *   - The user previously dismissed it (localStorage key 'ada_install_dismissed')
 *   - The browser does not fire `beforeinstallprompt` (e.g. iOS Safari)
 *
 * @decision DEC-PWA-002
 * @title InstallBanner uses deferred beforeinstallprompt — no custom UI timing
 * @status accepted
 * @rationale Browsers fire `beforeinstallprompt` only when the PWA criteria
 *   are met (HTTPS, manifest, service worker). Deferring the event and
 *   re-triggering it on user gesture is the correct W3C pattern. We store
 *   dismissal in localStorage (not sessionStorage) so the user is not
 *   re-prompted on every reload, only on a fresh session after clearing
 *   storage.
 */

import { useEffect, useState } from 'react'

const DISMISSED_KEY = 'ada_install_dismissed'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export function InstallBanner() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    // Already installed — running in standalone mode
    if (window.matchMedia('(display-mode: standalone)').matches) return

    // User already dismissed
    if (localStorage.getItem(DISMISSED_KEY) === 'true') return

    const handler = (e: Event) => {
      e.preventDefault()
      setDeferredPrompt(e as BeforeInstallPromptEvent)
      setVisible(true)
    }

    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  if (!visible || !deferredPrompt) return null

  const handleInstall = async () => {
    setVisible(false)
    await deferredPrompt.prompt()
    const { outcome } = await deferredPrompt.userChoice
    if (outcome === 'dismissed') {
      // User declined — record so we don't re-ask immediately
      localStorage.setItem(DISMISSED_KEY, 'true')
    }
    setDeferredPrompt(null)
  }

  const handleDismiss = () => {
    setVisible(false)
    setDeferredPrompt(null)
    localStorage.setItem(DISMISSED_KEY, 'true')
  }

  return (
    <div className="install-banner" role="banner" aria-label="Install Ada">
      <p className="install-banner__message">
        Install Ada on your device for quick access
      </p>
      <div className="install-banner__actions">
        <button
          className="install-banner__btn install-banner__btn--install"
          onClick={handleInstall}
          type="button"
        >
          Install
        </button>
        <button
          className="install-banner__btn install-banner__btn--dismiss"
          onClick={handleDismiss}
          type="button"
          aria-label="Dismiss install prompt"
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}
