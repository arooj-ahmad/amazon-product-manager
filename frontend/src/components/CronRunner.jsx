// src/components/CronRunner.jsx
// Professional UI for Manual Price Update

import { useState, useEffect } from 'react'
import { theme } from '../styles/theme'
import { usePriceUpdateStore } from '../store/priceUpdateStore'

export default function CronRunner({
  cronRunning,
  cronMessage,
  cronProgress,
  onRunCron,
}) {
  const { running, step, total, currentProduct, summary } = cronProgress || {}
  const { dismissSummary } = usePriceUpdateStore()

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

  const progressPercent = total > 0 ? Math.min((step / total) * 100, 95) : 0

  return (
    <div style={styles.card}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.iconBox}>
          <span style={styles.icon}>⚡</span>
        </div>
        <div>
          <h2 style={styles.title}>Update Prices & Inventory</h2>
          <p style={styles.subtitle}>
            Fetches the latest Amazon prices, recalculates markups, and pushes stock updates to Shopify.
          </p>
        </div>
      </div>

      {/* Action Button */}
      <button
        type="button"
        onClick={onRunCron}
        disabled={cronRunning}
        style={{
          ...styles.button,
          background: cronRunning ? '#b5b5b5' : '#008060',
          cursor: cronRunning ? 'not-allowed' : 'pointer',
        }}
      >
        {cronRunning ? (
          <>
            <span style={styles.spinner} />
            <span>Syncing Products...</span>
          </>
        ) : (
          <>
            <span style={{ fontSize: '18px' }}>🚀</span>
            <span>Run Price Update Now</span>
          </>
        )}
      </button>

      {/* Progress Bar */}
      {running && (
        <div style={styles.progressContainer}>
          <div style={styles.progressHeader}>
            <span style={styles.progressLabel}>
              {currentProduct ? `Syncing: ${currentProduct}` : 'Processing products...'}
            </span>
            <span style={styles.progressPercent}>
              {total > 0 ? `${step} / ${total}` : `⏱️ ${formatElapsed(elapsed)}`}
            </span>
          </div>

          <div style={styles.progressBarBg}>
            {total > 0 ? (
              <div
                style={{
                  ...styles.progressBarFill,
                  width: `${progressPercent}%`,
                }}
              />
            ) : (
              <div style={styles.progressBarIndeterminate} />
            )}
          </div>
          <p style={styles.progressHint}>
            This may take a few minutes. Please keep this page open.
          </p>
        </div>
      )}

      {/* Summary */}
      {summary && !running && (
        <div style={styles.summaryBox}>
          <div style={styles.summaryHeader}>
            <h3 style={styles.summaryTitle}>✅ Update Complete</h3>
            <button type="button" onClick={dismissSummary} style={styles.dismissBtn}>
              ✕
            </button>
          </div>

          <div style={styles.summaryGrid}>
            <div style={styles.summaryItem}>
              <span style={{ ...styles.summaryNum, color: '#202223' }}>
                {summary.total || 0}
              </span>
              <span style={styles.summaryLabel}>Total Products</span>
            </div>
            <div style={styles.summaryItem}>
              <span style={{ ...styles.summaryNum, color: '#008060' }}>
                {summary.price_changed ?? summary.updated ?? 0}
              </span>
              <span style={styles.summaryLabel}>Updated</span>
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

          {/* Details Dropdown */}
          {summary.results && summary.results.length > 0 ? (
            <details style={styles.details}>
              <summary style={styles.detailsSummary}>
                View detailed log ({summary.results.length})
              </summary>
              <div style={styles.detailsContent}>
                {summary.results.map((r, idx) => (
                  <div
                    key={idx}
                    style={{
                      ...styles.resultRow,
                      borderLeft: `3px solid ${
                        r.status === 'updated' ? '#008060' : r.status === 'skipped' ? '#f59e0b' : '#d72c0d'
                      }`,
                    }}
                  >
                    <span style={styles.resultAsin}>{r.asin}</span>
                    <span style={styles.resultTitle}>{r.title}</span>
                    <span
                      style={{
                        ...styles.resultStatus,
                        color: r.status === 'updated' ? '#008060' : r.status === 'skipped' ? '#f59e0b' : '#d72c0d',
                      }}
                    >
                      {r.status === 'updated' ? '✅' : r.status === 'skipped' ? '⏭️' : '❌'}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          ) : (
            <p style={styles.emptyResults}>All products were already up-to-date.</p>
          )}
        </div>
      )}

      {/* Error/Success Messages */}
      {cronMessage && (
        <div
          style={{
            ...styles.message,
            background: cronMessage.type === 'success' ? '#f0fdf4' : '#fef2f2',
            color: cronMessage.type === 'success' ? '#166534' : '#991b1b',
            border: `1px solid ${cronMessage.type === 'success' ? '#bbf7d0' : '#fecaca'}`,
          }}
        >
          <span style={{ fontSize: '18px' }}>
            {cronMessage.type === 'success' ? '✅' : '⚠️'}
          </span>
          {cronMessage.text}
        </div>
      )}
    </div>
  )
}

// ============================================
// Styles
// ============================================
const styles = {
  card: {
    background: 'white',
    borderRadius: '12px',
    border: '1px solid #e1e3e5',
    padding: '24px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  },
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '14px',
    marginBottom: '20px',
  },
  iconBox: {
    width: '44px',
    height: '44px',
    borderRadius: '10px',
    background: '#fff7ed',
    border: '1px solid #ffedd5',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  icon: { fontSize: '22px' },
  title: {
    fontSize: '18px',
    fontWeight: '700',
    color: '#202223',
    margin: '0 0 4px 0',
  },
  subtitle: {
    fontSize: '13px',
    color: '#6d7175',
    margin: 0,
    lineHeight: '1.5',
  },
  button: {
    width: '100%',
    padding: '14px 20px',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '15px',
    fontWeight: '600',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '10px',
    transition: 'all 0.2s',
    boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
  },
  spinner: {
    width: '18px',
    height: '18px',
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: 'white',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  message: {
    marginTop: '20px',
    padding: '16px',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '500',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },

  // Progress
  progressContainer: {
    marginTop: '20px',
    padding: '16px',
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
  },
  progressHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '10px',
    fontSize: '13px',
  },
  progressLabel: {
    color: '#334155',
    fontWeight: '600',
  },
  progressPercent: {
    color: '#0f172a',
    fontWeight: '700',
  },
  progressBarBg: {
    width: '100%',
    height: '8px',
    background: '#e2e8f0',
    borderRadius: '4px',
    overflow: 'hidden',
    position: 'relative',
  },
  progressBarFill: {
    height: '100%',
    background: '#008060',
    borderRadius: '4px',
    transition: 'width 0.4s ease-out',
  },
  progressBarIndeterminate: {
    height: '100%',
    width: '40%',
    background: '#008060',
    borderRadius: '4px',
    animation: 'indeterminate 1.5s ease-in-out infinite',
    position: 'absolute',
    top: 0,
    left: 0,
  },
  progressHint: {
    margin: '10px 0 0',
    fontSize: '12px',
    color: '#64748b',
    textAlign: 'center',
  },

  // Summary
  summaryBox: {
    marginTop: '24px',
    padding: '20px',
    background: '#f0fdf4',
    border: '1px solid #bbf7d0',
    borderRadius: '10px',
  },
  summaryHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
  },
  summaryTitle: {
    fontSize: '16px',
    fontWeight: '700',
    color: '#166534',
    margin: 0,
  },
  dismissBtn: {
    background: 'transparent',
    border: 'none',
    color: '#166534',
    fontSize: '18px',
    cursor: 'pointer',
    padding: '4px',
    lineHeight: 1,
  },
  summaryGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '12px',
    marginBottom: '16px',
  },
  summaryItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '12px',
    background: 'white',
    borderRadius: '8px',
    border: '1px solid #bbf7d0',
  },
  summaryNum: {
    fontSize: '22px',
    fontWeight: '700',
  },
  summaryLabel: {
    fontSize: '12px',
    color: '#166534',
    marginTop: '4px',
    fontWeight: '500',
  },
  details: {
    background: 'white',
    borderRadius: '8px',
    border: '1px solid #bbf7d0',
    overflow: 'hidden',
  },
  detailsSummary: {
    padding: '12px 16px',
    fontSize: '13px',
    fontWeight: '600',
    color: '#166534',
    cursor: 'pointer',
    userSelect: 'none',
  },
  detailsContent: {
    maxHeight: '300px',
    overflowY: 'auto',
    borderTop: '1px solid #bbf7d0',
    padding: '8px',
  },
  resultRow: {
    display: 'grid',
    gridTemplateColumns: '90px 1fr 30px',
    gap: '8px',
    padding: '10px 12px',
    fontSize: '13px',
    background: '#f8fafc',
    marginBottom: '4px',
    borderRadius: '6px',
    alignItems: 'center',
  },
  resultAsin: {
    fontWeight: '600',
    fontFamily: 'monospace',
    color: '#334155',
  },
  resultTitle: {
    color: '#475569',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  resultStatus: {
    fontWeight: '700',
    textAlign: 'center',
  },
  emptyResults: {
    fontSize: '13px',
    color: '#166534',
    margin: '0',
    textAlign: 'center',
    fontStyle: 'italic',
  },
}