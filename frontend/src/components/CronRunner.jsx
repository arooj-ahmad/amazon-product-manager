// src/components/CronRunner.jsx
// ✅ REDESIGNED: Modern UI for Manual Price & Inventory Update

import { useState, useEffect } from 'react'
import { theme } from '../styles/theme'
import { usePriceUpdateStore } from '../store/priceUpdateStore'

export default function CronRunner({
  cronRunning,
  cronMessage,
  cronProgress,
  onRunPriceCron,       // ✅ NAYA: Price button ke liye
  onRunInventoryCron,   // ✅ NAYA: Inventory button ke liye
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
        <div style={styles.headerTextContent}>
          <h2 style={styles.title}>Update Prices & Inventory</h2>
          <p style={styles.subtitle}>
            Update Amazon prices and inventory separately for your Shopify store.
          </p>
        </div>
      </div>

      {/* ✅ 2 Buttons Side-by-Side */}
      <div style={{ display: 'flex', gap: '15px', marginBottom: '20px', flexWrap: 'wrap' }}>
        
        {/* Price Update Button */}
        <button
          type="button"
          onClick={onRunPriceCron}
          disabled={cronRunning}
          style={{
            ...styles.button,
            flex: 1,
            minWidth: '200px',
            background: cronRunning ? '#9ca3af' : 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)', // Blue
            cursor: cronRunning ? 'not-allowed' : 'pointer',
            boxShadow: cronRunning ? 'none' : '0 4px 12px rgba(37, 99, 235, 0.25)',
          }}
        >
          {cronRunning ? (
            <>
              <span style={styles.spinner} />
              <span>Processing...</span>
            </>
          ) : (
            <>
              <span style={{ fontSize: '18px' }}>💰</span>
              <span>Run Price Update</span>
            </>
          )}
        </button>

        {/* Inventory Update Button */}
        <button
          type="button"
          onClick={onRunInventoryCron}
          disabled={cronRunning}
          style={{
            ...styles.button,
            flex: 1,
            minWidth: '200px',
            background: cronRunning ? '#9ca3af' : 'linear-gradient(135deg, #10b981 0%, #059669 100%)', // Green
            cursor: cronRunning ? 'not-allowed' : 'pointer',
            boxShadow: cronRunning ? 'none' : '0 4px 12px rgba(16, 185, 129, 0.25)',
          }}
        >
          {cronRunning ? (
            <>
              <span style={styles.spinner} />
              <span>Processing...</span>
            </>
          ) : (
            <>
              <span style={{ fontSize: '18px' }}>📦</span>
              <span>Run Inventory Update</span>
            </>
          )}
        </button>
      </div>

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
              <span style={{ ...styles.summaryNum, color: '#1e293b' }}>
                {summary.total || 0}
              </span>
              <span style={styles.summaryLabel}>Total Products</span>
            </div>
            <div style={styles.summaryItem}>
              <span style={{ ...styles.summaryNum, color: '#059669' }}>
                {summary.price_changed ?? summary.updated ?? 0}
              </span>
              <span style={styles.summaryLabel}>Updated</span>
            </div>
            <div style={styles.summaryItem}>
              <span style={{ ...styles.summaryNum, color: '#d97706' }}>
                {summary.skipped || 0}
              </span>
              <span style={styles.summaryLabel}>Skipped</span>
            </div>
            <div style={styles.summaryItem}>
              <span style={{ ...styles.summaryNum, color: '#dc2626' }}>
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
                        r.status === 'updated' ? '#10b981' : r.status === 'skipped' ? '#f59e0b' : '#ef4444'
                      }`,
                    }}
                  >
                    <span style={styles.resultAsin}>{r.asin}</span>
                    <span style={styles.resultTitle}>{r.title}</span>
                    <span
                      style={{
                        ...styles.resultStatus,
                        color: r.status === 'updated' ? '#059669' : r.status === 'skipped' ? '#d97706' : '#dc2626',
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
            background: cronMessage.type === 'success' ? '#ecfdf5' : '#fef2f2',
            color: cronMessage.type === 'success' ? '#065f46' : '#991b1b',
            border: `1px solid ${cronMessage.type === 'success' ? '#a7f3d0' : '#fecaca'}`,
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
// Styles (same as before)
// ============================================
const styles = {
  card: {
    background: '#ffffff',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
    padding: '28px',
    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
  },
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '16px',
    marginBottom: '24px',
  },
  iconBox: {
    width: '48px',
    height: '48px',
    borderRadius: '12px',
    background: 'linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%)',
    border: '1px solid #fed7aa',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    boxShadow: '0 2px 4px rgba(251, 146, 60, 0.1)',
  },
  icon: { fontSize: '24px' },
  headerTextContent: {
    flex: 1,
  },
  title: {
    fontSize: '20px',
    fontWeight: '700',
    color: '#0f172a',
    margin: '0 0 6px 0',
    letterSpacing: '-0.02em',
  },
  subtitle: {
    fontSize: '14px',
    color: '#64748b',
    margin: 0,
    lineHeight: '1.5',
  },
  button: {
    padding: '16px 24px',
    color: 'white',
    border: 'none',
    borderRadius: '10px',
    fontSize: '15px',
    fontWeight: '600',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '10px',
    transition: 'all 0.2s ease',
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
    marginTop: '24px',
    padding: '16px',
    borderRadius: '10px',
    fontSize: '14px',
    fontWeight: '500',
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  progressContainer: {
    marginTop: '24px',
    padding: '20px',
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '12px',
  },
  progressHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
    fontSize: '13px',
  },
  progressLabel: {
    color: '#334155',
    fontWeight: '600',
  },
  progressPercent: {
    color: '#0f172a',
    fontWeight: '700',
    background: '#e2e8f0',
    padding: '4px 10px',
    borderRadius: '20px',
    fontSize: '12px',
  },
  progressBarBg: {
    width: '100%',
    height: '10px',
    background: '#e2e8f0',
    borderRadius: '5px',
    overflow: 'hidden',
    position: 'relative',
  },
  progressBarFill: {
    height: '100%',
    background: 'linear-gradient(90deg, #10b981 0%, #059669 100%)',
    borderRadius: '5px',
    transition: 'width 0.4s ease-out',
  },
  progressBarIndeterminate: {
    height: '100%',
    width: '40%',
    background: 'linear-gradient(90deg, #10b981 0%, #059669 100%)',
    borderRadius: '5px',
    animation: 'indeterminate 1.5s ease-in-out infinite',
    position: 'absolute',
    top: 0,
    left: 0,
  },
  progressHint: {
    margin: '12px 0 0',
    fontSize: '12px',
    color: '#64748b',
    textAlign: 'center',
    fontStyle: 'italic',
  },
  summaryBox: {
    marginTop: '28px',
    padding: '24px',
    background: '#f0fdf4',
    border: '1px solid #bbf7d0',
    borderRadius: '12px',
  },
  summaryHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '20px',
  },
  summaryTitle: {
    fontSize: '18px',
    fontWeight: '700',
    color: '#065f46',
    margin: 0,
  },
  dismissBtn: {
    background: 'white',
    border: '1px solid #bbf7d0',
    color: '#065f46',
    fontSize: '14px',
    fontWeight: 'bold',
    cursor: 'pointer',
    padding: '4px 8px',
    borderRadius: '6px',
    lineHeight: 1,
    transition: 'all 0.2s',
  },
  summaryGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '16px',
    marginBottom: '20px',
  },
  summaryItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '16px',
    background: 'white',
    borderRadius: '10px',
    border: '1px solid #d1fae5',
    boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
  },
  summaryNum: {
    fontSize: '24px',
    fontWeight: '800',
  },
  summaryLabel: {
    fontSize: '12px',
    color: '#047857',
    marginTop: '6px',
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  details: {
    background: 'white',
    borderRadius: '10px',
    border: '1px solid #bbf7d0',
    overflow: 'hidden',
  },
  detailsSummary: {
    padding: '14px 18px',
    fontSize: '14px',
    fontWeight: '600',
    color: '#047857',
    cursor: 'pointer',
    userSelect: 'none',
    outline: 'none',
  },
  detailsContent: {
    maxHeight: '300px',
    overflowY: 'auto',
    borderTop: '1px solid #bbf7d0',
    padding: '12px',
    background: '#f8fafc',
  },
  resultRow: {
    display: 'grid',
    gridTemplateColumns: '90px 1fr 30px',
    gap: '12px',
    padding: '12px 14px',
    fontSize: '13px',
    background: 'white',
    marginBottom: '8px',
    borderRadius: '8px',
    alignItems: 'center',
    boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
  },
  resultAsin: {
    fontWeight: '700',
    fontFamily: 'monospace',
    color: '#334155',
    fontSize: '12px',
  },
  resultTitle: {
    color: '#475569',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    fontWeight: '500',
  },
  resultStatus: {
    fontWeight: '700',
    textAlign: 'center',
    fontSize: '16px',
  },
  emptyResults: {
    fontSize: '14px',
    color: '#047857',
    margin: '0',
    textAlign: 'center',
    fontStyle: 'italic',
    padding: '16px',
    background: 'white',
    borderRadius: '8px',
    border: '1px solid #d1fae5',
  },
}