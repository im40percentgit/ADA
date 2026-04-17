/**
 * TreatmentPlan — view and manage treatment plans for a patient.
 *
 * Two modes:
 *   1. List mode (no planId prop): shows all plans for the patient, each
 *      clickable to navigate into detail mode.
 *   2. Detail mode (planId provided): fetches a single plan and renders
 *      its goals, progress bars, interventions, and add-goal / add-intervention
 *      forms.
 *
 * Uses Card, Button, Badge, Input, ProgressBar from the shared UI library.
 *
 * @decision DEC-FRONTEND-070
 * @title TreatmentPlan switches between list and detail via planId prop
 * @status accepted
 * @rationale Keeping both modes in one component avoids duplicating the
 *   loading/error patterns and gives the parent (ClinicianPortal) a simple
 *   interface: omit planId for list, provide planId for detail. Internal
 *   state transitions (clicking a plan) are surfaced through a selectedPlanId
 *   local state, re-using the same fetch-and-render logic.
 */

import { useState, useEffect, useCallback } from 'react'
import { Card } from './ui/Card'
import { Button } from './ui/Button'
import { Badge } from './ui/Badge'
import { Input } from './ui/Input'
import { ProgressBar } from './ui/ProgressBar'
import { Skeleton } from './ui/Skeleton'
import { EmptyState } from './ui/EmptyState'
import { ErrorState } from './ui/ErrorState'
import {
  listTreatmentPlans,
  getTreatmentPlan,
  createTreatmentPlan,
  addTreatmentGoal,
  addIntervention,
} from '../api/client'
import type { TreatmentPlan as TreatmentPlanType, TreatmentGoal, TreatmentIntervention } from '../types'
import { usePdfExport } from '../hooks/usePdfExport'

export interface TreatmentPlanProps {
  patientId: string
  planId?: string
  onBack: () => void
}

const statusVariant: Record<string, 'success' | 'warning' | 'neutral' | 'info'> = {
  active: 'success',
  met: 'success',
  completed: 'info',
  archived: 'neutral',
  unmet: 'warning',
  deferred: 'neutral',
}

const metricLabels: Record<string, string> = {
  phq9: 'PHQ-9',
  gad7: 'GAD-7',
  who5: 'WHO-5',
  cognitive: 'Cognitive',
  custom: 'Custom',
}

function formatTargetDisplay(goal: TreatmentGoal): string | null {
  if (!goal.target_metric || goal.target_value === null) return null
  const label = metricLabels[goal.target_metric] ?? goal.target_metric
  return `${label} ${goal.target_operator} ${goal.target_value}`
}

function goalProgress(goal: TreatmentGoal): number {
  if (goal.target_value === null || goal.current_value === null) return 0
  if (goal.target_value === 0) return goal.current_value === 0 ? 100 : 0

  // For "less than" targets, progress is inverted (lower is better)
  if (goal.target_operator === '<' || goal.target_operator === '<=') {
    // If current is already at or below target, 100%
    if (goal.current_value <= goal.target_value) return 100
    // Scale: assume starting point is 2x target as a reasonable max
    const maxVal = goal.target_value * 2
    const progress = ((maxVal - goal.current_value) / (maxVal - goal.target_value)) * 100
    return Math.max(0, Math.min(100, progress))
  }

  // For "greater than" targets, progress is direct ratio
  const progress = (goal.current_value / goal.target_value) * 100
  return Math.max(0, Math.min(100, progress))
}

function InterventionItem({ intervention }: { intervention: TreatmentIntervention }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '4px 0',
        fontSize: 'var(--size-sm)',
      }}
    >
      <span style={{ color: 'var(--color-text-primary)' }}>{intervention.description}</span>
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        {intervention.frequency && (
          <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--size-xs)' }}>
            {intervention.frequency}
          </span>
        )}
        <Badge variant={statusVariant[intervention.status] ?? 'neutral'}>{intervention.status}</Badge>
      </div>
    </div>
  )
}

function GoalCard({
  goal,
  onAddIntervention,
}: {
  goal: TreatmentGoal
  onAddIntervention: (goalId: string, desc: string, freq: string) => void
}) {
  const [showForm, setShowForm] = useState(false)
  const [intDesc, setIntDesc] = useState('')
  const [intFreq, setIntFreq] = useState('')

  const targetDisplay = formatTargetDisplay(goal)
  const progress = goalProgress(goal)

  const handleSubmit = () => {
    if (!intDesc.trim()) return
    onAddIntervention(goal.id, intDesc.trim(), intFreq.trim())
    setIntDesc('')
    setIntFreq('')
    setShowForm(false)
  }

  return (
    <Card style={{ marginBottom: 'var(--space-sm)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
        <div>
          <strong data-testid="goal-description">{goal.description}</strong>
          {targetDisplay && (
            <span
              style={{ marginLeft: '8px', color: 'var(--color-text-muted)', fontSize: 'var(--size-sm)' }}
              data-testid="goal-target"
            >
              {targetDisplay}
            </span>
          )}
        </div>
        <Badge variant={statusVariant[goal.status] ?? 'neutral'}>{goal.status}</Badge>
      </div>

      {goal.current_value !== null && goal.target_value !== null && (
        <div style={{ marginBottom: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--size-xs)', color: 'var(--color-text-muted)', marginBottom: '4px' }}>
            <span>Current: {goal.current_value}</span>
            <span>Target: {goal.target_value}</span>
          </div>
          <ProgressBar value={progress} aria-label={`Progress for ${goal.description}`} />
        </div>
      )}

      {goal.interventions.length > 0 && (
        <div style={{ marginTop: '8px', borderTop: '1px solid var(--color-border)', paddingTop: '8px' }}>
          <span style={{ fontSize: 'var(--size-xs)', color: 'var(--color-text-muted)', fontWeight: 600 }}>
            Interventions
          </span>
          {goal.interventions.map((int) => (
            <InterventionItem key={int.id} intervention={int} />
          ))}
        </div>
      )}

      {showForm ? (
        <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <Input
            label="Intervention description"
            value={intDesc}
            onChange={(e) => setIntDesc(e.target.value)}
            placeholder="Describe the intervention..."
          />
          <Input
            label="Frequency"
            value={intFreq}
            onChange={(e) => setIntFreq(e.target.value)}
            placeholder="e.g. weekly, daily"
          />
          <div style={{ display: 'flex', gap: '8px' }}>
            <Button size="sm" onClick={handleSubmit} disabled={!intDesc.trim()}>
              Add Intervention
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div style={{ marginTop: '8px' }}>
          <Button size="sm" variant="ghost" onClick={() => setShowForm(true)}>
            + Add Intervention
          </Button>
        </div>
      )}
    </Card>
  )
}

export function TreatmentPlan({ patientId, planId, onBack }: TreatmentPlanProps) {
  const [plans, setPlans] = useState<TreatmentPlanType[]>([])
  const [selectedPlan, setSelectedPlan] = useState<TreatmentPlanType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { exportToPdf, exporting } = usePdfExport()

  // Add goal form state
  const [showGoalForm, setShowGoalForm] = useState(false)
  const [goalDesc, setGoalDesc] = useState('')
  const [goalMetric, setGoalMetric] = useState<string>('')
  const [goalOperator, setGoalOperator] = useState('<')
  const [goalTarget, setGoalTarget] = useState('')
  const [goalDueDate, setGoalDueDate] = useState('')

  // Create plan form state
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newPlanTitle, setNewPlanTitle] = useState('')

  const [activePlanId, setActivePlanId] = useState<string | undefined>(planId)

  const fetchPlans = useCallback(async () => {
    try {
      setLoading(true)
      const data = await listTreatmentPlans(patientId)
      setPlans(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load treatment plans')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  const fetchPlan = useCallback(async (id: string) => {
    try {
      setLoading(true)
      const data = await getTreatmentPlan(id)
      setSelectedPlan(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load treatment plan')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (activePlanId) {
      fetchPlan(activePlanId)
    } else {
      fetchPlans()
    }
  }, [activePlanId, fetchPlan, fetchPlans])

  const handleSelectPlan = (id: string) => {
    setActivePlanId(id)
  }

  const handleBackToList = () => {
    if (planId) {
      onBack()
    } else {
      setActivePlanId(undefined)
      setSelectedPlan(null)
      fetchPlans()
    }
  }

  const handleCreatePlan = async () => {
    if (!newPlanTitle.trim()) return
    try {
      const plan = await createTreatmentPlan(patientId, newPlanTitle.trim())
      setPlans((prev) => [...prev, plan])
      setNewPlanTitle('')
      setShowCreateForm(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create plan')
    }
  }

  const handleAddGoal = async () => {
    if (!selectedPlan || !goalDesc.trim()) return
    try {
      const goal = await addTreatmentGoal(selectedPlan.id, {
        description: goalDesc.trim(),
        target_metric: (goalMetric as TreatmentGoal['target_metric']) || null,
        target_operator: goalOperator as TreatmentGoal['target_operator'],
        target_value: goalTarget ? Number(goalTarget) : null,
        current_value: null,
        status: 'active',
        due_date: goalDueDate || null,
      })
      setSelectedPlan((prev) =>
        prev ? { ...prev, goals: [...prev.goals, goal] } : prev,
      )
      setGoalDesc('')
      setGoalMetric('')
      setGoalOperator('<')
      setGoalTarget('')
      setGoalDueDate('')
      setShowGoalForm(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add goal')
    }
  }

  const handleAddIntervention = async (goalId: string, description: string, frequency: string) => {
    try {
      const intervention = await addIntervention(goalId, {
        description,
        frequency: frequency || null,
        status: 'active',
      })
      setSelectedPlan((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          goals: prev.goals.map((g) =>
            g.id === goalId
              ? { ...g, interventions: [...g.interventions, intervention] }
              : g,
          ),
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add intervention')
    }
  }

  if (loading) {
    return (
      <div aria-busy="true" style={{ padding: 'var(--space-md)' }}>
        <Skeleton variant="block" height="200px" aria-label="Loading treatment plan…" />
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: 'var(--space-md)' }}>
        <ErrorState
          title="Could not load treatment plan"
          message={error}
          action={<Button variant="ghost" onClick={onBack}>Go back</Button>}
        />
      </div>
    )
  }

  // Detail view
  if (selectedPlan) {
    return (
      <section aria-label="Treatment Plan Detail" style={{ padding: 'var(--space-md)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: 'var(--space-md)' }}>
          <Button variant="ghost" size="sm" onClick={handleBackToList}>
            Back
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => exportToPdf('export-treatment-plan', `treatment-plan-${selectedPlan.id}.pdf`)}
            disabled={exporting}
          >
            {exporting ? 'Exporting...' : 'Download PDF'}
          </Button>
          <h2 style={{ margin: 0, fontSize: 'var(--size-h2)' }} data-testid="plan-title">
            {selectedPlan.title}
          </h2>
          <Badge variant={statusVariant[selectedPlan.status] ?? 'neutral'}>
            {selectedPlan.status}
          </Badge>
        </div>

        <div id="export-treatment-plan">

        {selectedPlan.goals.length === 0 && (
          <EmptyState
            icon="🎯"
            title="No goals yet"
            description="Add a goal to begin tracking progress."
            tone="info"
          />
        )}

        {selectedPlan.goals.map((goal) => (
          <GoalCard
            key={goal.id}
            goal={goal}
            onAddIntervention={handleAddIntervention}
          />
        ))}

        {showGoalForm ? (
          <Card style={{ marginTop: 'var(--space-md)' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 'var(--size-body)' }}>Add Goal</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <Input
                label="Goal description"
                value={goalDesc}
                onChange={(e) => setGoalDesc(e.target.value)}
                placeholder="Describe the treatment goal..."
              />
              <div style={{ display: 'flex', gap: '8px' }}>
                <label style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
                  <span style={{ fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)', marginBottom: '4px' }}>
                    Target metric
                  </span>
                  <select
                    value={goalMetric}
                    onChange={(e) => setGoalMetric(e.target.value)}
                    aria-label="Target metric"
                    style={{
                      background: 'var(--color-bg-elevated)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-input)',
                      height: 'var(--touch-target-min)',
                      padding: '0 var(--space-sm)',
                      color: 'var(--color-text-primary)',
                      fontSize: 'var(--size-body)',
                    }}
                  >
                    <option value="">None</option>
                    <option value="phq9">PHQ-9</option>
                    <option value="gad7">GAD-7</option>
                    <option value="who5">WHO-5</option>
                    <option value="cognitive">Cognitive</option>
                    <option value="custom">Custom</option>
                  </select>
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', width: '80px' }}>
                  <span style={{ fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)', marginBottom: '4px' }}>
                    Operator
                  </span>
                  <select
                    value={goalOperator}
                    onChange={(e) => setGoalOperator(e.target.value)}
                    aria-label="Target operator"
                    style={{
                      background: 'var(--color-bg-elevated)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-input)',
                      height: 'var(--touch-target-min)',
                      padding: '0 var(--space-sm)',
                      color: 'var(--color-text-primary)',
                      fontSize: 'var(--size-body)',
                    }}
                  >
                    <option value="<">&lt;</option>
                    <option value=">">&gt;</option>
                    <option value="<=">&lt;=</option>
                    <option value=">=">&gt;=</option>
                  </select>
                </label>
                <Input
                  label="Target value"
                  type="number"
                  value={goalTarget}
                  onChange={(e) => setGoalTarget(e.target.value)}
                  style={{ width: '100px' }}
                />
              </div>
              <Input
                label="Due date"
                type="date"
                value={goalDueDate}
                onChange={(e) => setGoalDueDate(e.target.value)}
              />
              <div style={{ display: 'flex', gap: '8px' }}>
                <Button onClick={handleAddGoal} disabled={!goalDesc.trim()}>
                  Add Goal
                </Button>
                <Button variant="ghost" onClick={() => setShowGoalForm(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          </Card>
        ) : (
          <div style={{ marginTop: 'var(--space-md)' }}>
            <Button onClick={() => setShowGoalForm(true)}>
              + Add Goal
            </Button>
          </div>
        )}

        </div>
      </section>
    )
  }

  // List view
  return (
    <section aria-label="Treatment Plans" style={{ padding: 'var(--space-md)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-md)' }}>
        <h2 style={{ margin: 0, fontSize: 'var(--size-h2)' }}>Treatment Plans</h2>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button variant="ghost" size="sm" onClick={onBack}>Back</Button>
          <Button size="sm" onClick={() => setShowCreateForm(true)}>+ New Plan</Button>
        </div>
      </div>

      {showCreateForm && (
        <Card style={{ marginBottom: 'var(--space-md)' }}>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
            <Input
              label="Plan title"
              value={newPlanTitle}
              onChange={(e) => setNewPlanTitle(e.target.value)}
              placeholder="Enter plan title..."
            />
            <Button onClick={handleCreatePlan} disabled={!newPlanTitle.trim()}>
              Create
            </Button>
            <Button variant="ghost" onClick={() => setShowCreateForm(false)}>
              Cancel
            </Button>
          </div>
        </Card>
      )}

      {plans.length === 0 && (
        <EmptyState
          icon="🎯"
          title="No treatment plans yet"
          description="Create a plan to begin tracking treatment goals and interventions."
          tone="info"
        />
      )}

      {plans.map((plan) => (
        <Card
          key={plan.id}
          onClick={() => handleSelectPlan(plan.id)}
          style={{ marginBottom: 'var(--space-sm)' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <strong>{plan.title}</strong>
            <Badge variant={statusVariant[plan.status] ?? 'neutral'}>{plan.status}</Badge>
          </div>
          <div style={{ fontSize: 'var(--size-sm)', color: 'var(--color-text-muted)', marginTop: '4px' }}>
            {plan.goals.length} goal{plan.goals.length !== 1 ? 's' : ''}
          </div>
        </Card>
      ))}
    </section>
  )
}
