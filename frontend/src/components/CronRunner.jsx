// src/components/CronRunner.jsx
// + ✅ NAYA: Progress bar while running
// + ✅ NAYA: Summary + detailed results after complete
// + ✅ FIXED: Indeterminate progress when total unknown
// + ✅ FIXED: Elapsed time tracker
// + ✅ FIXED: Empty results message
// + ✅ NAYA v2: Dismiss button (✕) — summary manually hatane ke liye

import { useState, useEffect } from 'react'
import { theme } from '../styles/theme'
import { usePriceUpdateStore } from '../store/priceUpdateStore'

export default function CronRunner({
  cronRunning,
  cronMessage,
  cronProgress,
  onRunCron,
}) {
  const { running, step, total, currentProduct, summary } =
    cronProgress || {}

  // ✅ NAYA: Dismiss handler — Zustand store se
  const { dismissSummary } = usePriceUpdateStore()

  // ✅ NAYA: Elapsed time tracker
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!running) {
      setElapsed(0)
      return
    }

    const startTime = Date.now()
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)

    return () => clearInterval(interval)
  }, [running])

  const formatElapsed = (secs) => {
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return m > 0 ? `${m}m ${s}s` : `${s}s`
  }

  const progressPercent =
    total > 0 ? Math.min((step / total) * 100, 95) : 0

  return (
    <div style={styles.card}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.iconBox}>
          <span style={styles.icon}>⚡</span>
        </div>
        <div style={styles.headerText}>
          <h3 style={styles.title}>Manual Price Update</h3>
          <p style={styles.subtitle}>
            Fetch latest Amazon prices and sync your Shopify products
          </p>
        </div>
      </div>

      {/* Button */}
      <button
        type="button"
        onClick={onRunCron}
        disabled={cronRunning}
        style={{
          ...styles.button,
          background: cronRunning
            ? 'linear-gradient(135deg, #b5b5b5 0%, #d1d1d1 100%)'
            : theme.colors.gradientPrimary,
          cursor: cronRunning ? 'not-allowed' : 'pointer',
          transform: cronRunning ? 'none' : 'translateY(0)',
        }}
        onMouseEnter={(e) => {
          if (!cronRunning) {
            e.currentTarget.style.transform = 'translateY(-2px)'
            e.currentTarget.style.boxShadow = theme.shadows.lg
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)'
          e.currentTarget.style.boxShadow = theme.shadows.md
        }}
      >
        {cronRunning ? (
          <>
            <span style={styles.spinner} />
            <span>Running Price Update...</span>
          </>
        ) : (
          <>
            <span style={styles.buttonIcon}>🚀</span>
            <span>Run Price Update Now</span>
          </>
        )}
      </button>

      {/* ✅ Progress (indeterminate when total unknown) */}
      {running && (
        <div style={styles.progressContainer}>
          <div style={styles.progressHeader}>
            <span style={styles.progressLabel}>
              {currentProduct || 'Processing products...'}
            </span>
            <span style={styles.progressPercent}>
              {total > 0
                ? `${step} / ${total}`
                : `⏱️ ${formatElapsed(elapsed)}`}
            </span>
          </div>

          {total > 0 ? (
            <div style={styles.progressBarBg}>
              <div
                style={{
                  ...styles.progressBarFill,
                  width: `${progressPercent}%`,
                }}
              />
            </div>
          ) : (
            <div style={styles.progressBarBg}>
              <div style={styles.progressBarIndeterminate} />
            </div>
          )}

          <p style={styles.progressHint}>
            Yeh 1–5 minute lag sakta hai. Tab tak app open rakhein.
          </p>
        </div>
      )}

      {/* ✅ Summary (jab complete ho) */}
      {summary && !running && (
        <div style={styles.summaryBox}>
          {/* ✅ NAYA: Header with dismiss button */}
          <div style={styles.summaryHeader}>
            <div style={styles.summaryTitle}>
              ✅ Price Update Complete
            </div>
            <button
              type="button"
              onClick={dismissSummary}
              style={styles.dismissBtn}
              title="Dismiss summary"
            >
              ✕
            </button>
          </div>

          <div style={styles.summaryGrid}>
            <div style={styles.summaryItem}>
              <span style={styles.summaryNum}>{summary.total || 0}</span>
              <span style={styles.summaryLabel}>Total</span>
            </div>
            <div style={styles.summaryItem}>
              <span style={{ ...styles.summaryNum, color: '#008060' }}>
                {summary.price_changed ?? summary.updated ?? 0}
              </span>
              <span style={styles.summaryLabel}>Changed</span>
            </div>
            <div style={styles.summaryItem}>
              <span style={{ ...styles.summaryNum, color: '#f59e0b' }}>
                {summary.skipped || 0}
              </span>
              <span style={styles.summaryLabel}>Skipped</span>
            </div>
            <div style={styles.summaryItem}>
              <span style={{ ...styles.summaryNum, color: '#d72c0d' }}>
                {summary.errors || 0}
              </span>
              <span style={styles.summaryLabel}>Errors</span>
            </div>
          </div>

          {/* Detailed results */}
          {summary.results && summary.results.length > 0 ? (
            <details style={styles.details}>
              <summary style={styles.detailsSummary}>
                View detailed results ({summary.results.length})
              </summary>
              <div style={styles.detailsContent}>
                {summary.results.map((r, idx) => (
                  <div
                    key={idx}
                    style={{
                      ...styles.resultRow,
                      borderLeft: `3px solid ${
                        r.status === 'updated'
                          ? '#008060'
                          : r.status === 'skipped'
                            ? '#f59e0b'
                            : '#d72c0d'
                      }`,
                    }}
                  >
                    <span style={styles.resultAsin}>{r.asin}</span>
                    <span style={styles.resultTitle}>{r.title}</span>
                    <span
                      style={{
                        ...styles.resultStatus,
                        color:
                          r.status === 'updated'
                            ? '#008060'
                            : r.status === 'skipped'
                              ? '#f59e0b'
                              : '#d72c0d',
                      }}
                    >
                      {r.status === 'updated'
                        ? '✅ Updated'
                        : r.status === 'skipped'
                          ? '⏭️ Skipped'
                          : '❌ Error'}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          ) : (
            <p style={styles.emptyResults}>
              Sab products already up-to-date the ✅
            </p>
          )}
        </div>
      )}

      {/* Message */}
      {cronMessage && (
        <div
          style={{
            ...styles.message,
            background:
              cronMessage.type === 'success'
                ? theme.colors.successBg
                : theme.colors.errorBg,
            color:
              cronMessage.type === 'success'
                ? theme.colors.success
                : theme.colors.error,
            border: `1px solid ${
              cronMessage.type === 'success'
                ? theme.colors.successBorder
                : theme.colors.errorBorder
            }`,
          }}
        >
          {cronMessage.text}
        </div>
      )}
    </div>
  )
}

const styles = {
  card: {
    background: theme.colors.bgCard,
    borderRadius: theme.radii.lg,
    border: `1px solid ${theme.colors.border}`,
    padding: '20px',
    marginBottom: '20px',
    boxShadow: theme.shadows.sm,
  },
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '12px',
    marginBottom: '16px',
  },
  iconBox: {
    width: '40px',
    height: '40px',
    borderRadius: theme.radii.md,
    background: 'linear-gradient(135deg, #fff8e6 0%, #ffefc2 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  icon: { fontSize: '20px' },
  headerText: { flex: 1 },
  title: {
    fontSize: '15px',
    fontWeight: '600',
    color: theme.colors.text,
    margin: '0 0 4px',
  },
  subtitle: {
    fontSize: '13px',
    color: theme.colors.textSecondary,
    margin: 0,
    lineHeight: '1.4',
  },
  button: {
    width: '100%',
    padding: '14px 20px',
    color: 'white',
    border: 'none',
    borderRadius: theme.radii.md,
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: theme.transitions.fast,
    boxShadow: theme.shadows.md,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
  },
  buttonIcon: { fontSize: '16px' },
  spinner: {
    width: '16px',
    height: '16px',
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: 'white',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  message: {
    marginTop: '12px',
    padding: '12px 16px',
    borderRadius: theme.radii.md,
    fontSize: '13px',
    fontWeight: '500',
    textAlign: 'center',
  },

  // ✅ Progress styles
  progressContainer: {
    marginTop: '16px',
    padding: '14px',
    background: '#eff6ff',
    border: '1px solid #bfdbfe',
    borderRadius: theme.radii.md,
  },
  progressHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '8px',
    fontSize: '13px',
  },
  progressLabel: {
    color: '#1e40af',
    fontWeight: '600',
  },
  progressPercent: {
    color: '#1e40af',
    fontWeight: '700',
    fontSize: '14px',
  },
  progressBarBg: {
    width: '100%',
    height: '8px',
    background: 'white',
    borderRadius: '4px',
    overflow: 'hidden',
    border: '1px solid #bfdbfe',
    position: 'relative',
  },
  progressBarFill: {
    height: '100%',
    background: 'linear-gradient(90deg, #008060 0%, #006e52 100%)',
    borderRadius: '4px',
    transition: 'width 0.4s ease-out',
  },
  progressBarIndeterminate: {
    height: '100%',
    width: '40%',
    background:
      'linear-gradient(90deg, #008060 0%, #006e52 50%, #008060 100%)',
    borderRadius: '4px',
    animation: 'indeterminate 1.5s ease-in-out infinite',
    position: 'absolute',
    top: 0,
    left: 0,
  },
  progressHint: {
    margin: '8px 0 0',
    fontSize: '11px',
    color: '#1e40af',
    textAlign: 'center',
    opacity: 0.8,
  },

  // ✅ Summary styles
  summaryBox: {
    marginTop: '16px',
    padding: '16px',
    background: '#f0fdf4',
    border: '1px solid #86efac',
    borderRadius: theme.radii.md,
  },

  // ✅ NAYA: Summary header with dismiss button
  summaryHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
  },
  summaryTitle: {
    fontSize: '14px',
    fontWeight: '700',
    color: '#166534',
    margin: 0,
  },
  dismissBtn: {
    background: 'transparent',
    border: 'none',
    color: '#166534',
    fontSize: '18px',
    fontWeight: '700',
    cursor: 'pointer',
    padding: '2px 8px',
    borderRadius: '4px',
    lineHeight: 1,
    transition: 'background 0.15s ease',
  },

  summaryGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '10px',
    marginBottom: '12px',
  },
  summaryItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '10px 6px',
    background: 'white',
    borderRadius: '6px',
    border: '1px solid #86efac',
  },
  summaryNum: {
    fontSize: '20px',
    fontWeight: '700',
    color: theme.colors.text,
  },
  summaryLabel: {
    fontSize: '11px',
    color: theme.colors.textSecondary,
    marginTop: '2px',
    textAlign: 'center',
  },

  // ✅ Details
  details: {
    marginTop: '10px',
    background: 'white',
    borderRadius: '6px',
    border: '1px solid #86efac',
    overflow: 'hidden',
  },
  detailsSummary: {
    padding: '10px 12px',
    fontSize: '12px',
    fontWeight: '600',
    color: '#166534',
    cursor: 'pointer',
    userSelect: 'none',
  },
  detailsContent: {
    maxHeight: '280px',
    overflowY: 'auto',
    padding: '8px',
  },
  resultRow: {
    display: 'grid',
    gridTemplateColumns: '80px 1fr 90px',
    gap: '8px',
    padding: '8px 10px',
    fontSize: '12px',
    background: '#fafafa',
    marginBottom: '4px',
    borderRadius: '4px',
    alignItems: 'center',
  },
  resultAsin: {
    fontWeight: '600',
    color: theme.colors.text,
    fontFamily: 'monospace',
    fontSize: '11px',
  },
  resultTitle: {
    color: theme.colors.textSecondary,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  resultStatus: {
    fontWeight: '600',
    fontSize: '11px',
    textAlign: 'right',
  },
  emptyResults: {
    fontSize: '12px',
    color: '#166534',
    marginTop: '8px',
    marginBottom: 0,
    textAlign: 'center',
    fontStyle: 'italic',
  },
}