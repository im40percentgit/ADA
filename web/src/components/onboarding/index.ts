/**
 * onboarding/index.ts — barrel export for all onboarding screen components.
 *
 * Re-exports each screen so consumers can import from a single path:
 *   import { OnboardingWelcome, OnboardingName } from './onboarding'
 */

export { OnboardingWelcome } from './OnboardingWelcome'
export { OnboardingName } from './OnboardingName'
export { OnboardingVoice } from './OnboardingVoice'
export { OnboardingPersonality } from './OnboardingPersonality'
export { OnboardingChat } from './OnboardingChat'
export { OnboardingWellbeing } from './OnboardingWellbeing'
export { OnboardingCognitive } from './OnboardingCognitive'
export { OnboardingCircle } from './OnboardingCircle'
export { OnboardingDashboard } from './OnboardingDashboard'
export { OnboardingNotifications } from './OnboardingNotifications'
export { OnboardingFlow } from './OnboardingFlow'

export type { OnboardingWelcomeProps } from './OnboardingWelcome'
export type { OnboardingNameProps } from './OnboardingName'
export type { OnboardingVoiceProps } from './OnboardingVoice'
export type { OnboardingPersonalityProps, PersonalitySettings } from './OnboardingPersonality'
export type { OnboardingChatProps } from './OnboardingChat'
export type { OnboardingWellbeingProps } from './OnboardingWellbeing'
export type { OnboardingCognitiveProps } from './OnboardingCognitive'
export type { OnboardingCircleProps } from './OnboardingCircle'
export type { OnboardingDashboardProps } from './OnboardingDashboard'
export type { OnboardingNotificationsProps } from './OnboardingNotifications'
export type { OnboardingFlowProps } from './OnboardingFlow'
