// src/components/PlanCard.jsx
import { styles, theme } from '../styles/theme'

export default function PlanCard({
  plan,
  onSubscribe,
  isSubscribing,       // global subscribing state
  subscribingPlanKey,  // ← NEW: which plan is currently loading
}) {
  // ✅ Check if this card is currently loading
  const isThisLoading = isSubscribing && subscribingPlanKey === plan.key

  return (
    <div style={styles.planCard}>
      <h3
        style={{
          fontSize: '20px',
          fontWeight: '600',
          marginBottom: '8px',
          margin: '0 0 8px 0',
        }}
      >
        {plan.name}
      </h3>
      <p
        style={{
          fontSize: '32px',
          fontWeight: 'bold',
          marginBottom: '8px',
          margin: '0 0 8px 0',
        }}
      >
        ${plan.price}
        <span
          style={{
            fontSize: '14px',
            fontWeight: 'normal',
            color: theme.colors.textSecondary,
          }}
        >
          /month
        </span>
      </p>

      {plan.trial_days > 0 && (
        <p
          style={{
            fontSize: '13px',
            color: theme.colors.successText,
            marginBottom: '16px',
            fontWeight: '500',
            margin: '0 0 16px 0',
          }}
        >
          {plan.trial_days}-day free trial
        </p>
      )}

      <ul
        style={{
          listStyle: 'none',
          padding: 0,
          marginBottom: '20px',
          margin: '0 0 20px 0',
        }}
      >
        {(plan.features || []).map((f) => (
          <li
            key={f}
            style={{
              padding: '6px 0',
              fontSize: '14px',
              color: theme.colors.textPrimary,
            }}
          >
            ✓ {f}
          </li>
        ))}
      </ul>

      {/* ✅ Only this button shows its own loading state */}
      <button
        onClick={() => onSubscribe(plan.key)}
        disabled={isSubscribing}  // ✅ All buttons disabled — but only this one shows loading
        style={{
          ...styles.primaryBtn,
          background: isThisLoading
            ? theme.colors.primaryDisabled
            : theme.colors.primary,
          cursor: isSubscribing ? 'not-allowed' : 'pointer',
        }}
      >
        {isThisLoading ? '⏳ Redirecting...' : 'Start Free Trial'}
      </button>
    </div>
  )
}