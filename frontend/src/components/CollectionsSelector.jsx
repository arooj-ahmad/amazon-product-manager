// src/components/CollectionsSelector.jsx
import { useState } from 'react'
import { theme } from '../styles/theme'

export default function CollectionsSelector({
  collections = [],
  selectedCollections = new Set(),
  loading = false,
  onToggle,
  onClear,
  onRefresh,
}) {
  const [searchQuery, setSearchQuery] = useState('')

  const filtered = collections.filter((col) =>
    col.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleSelectAll = () => {
    filtered.forEach((col) => {
      if (!selectedCollections.has(col.id)) {
        onToggle(col.id)
      }
    })
  }

  // Loading
  if (loading) {
    return (
      <div style={styles.card}>
        <div style={styles.header}>
          <div style={styles.iconBox}>
            <span style={styles.icon}>📁</span>
          </div>
          <div>
            <h3 style={styles.title}>Add to Collections</h3>
            <p style={styles.subtitle}>Loading your collections...</p>
          </div>
        </div>
        <div style={styles.loadingBox}>
          <div style={styles.spinner} />
          <span>Loading collections...</span>
        </div>
      </div>
    )
  }

  // Empty
  if (collections.length === 0) {
    return (
      <div style={styles.card}>
        <div style={styles.header}>
          <div style={styles.iconBox}>
            <span style={styles.icon}>📁</span>
          </div>
          <div>
            <h3 style={styles.title}>Add to Collections</h3>
            <p style={styles.subtitle}>
              No collections found in your Shopify store
            </p>
          </div>
        </div>
        <div style={styles.emptyBox}>
          <span style={styles.emptyIcon}>📭</span>
          <p style={styles.emptyText}>
            Create collections in Shopify Admin first
          </p>
          {onRefresh && (
            <button onClick={onRefresh} style={styles.refreshBtn}>
              🔄 Refresh Collections
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div style={styles.card}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.iconBox}>
          <span style={styles.icon}>📁</span>
        </div>
        <div style={styles.headerContent}>
          <h3 style={styles.title}>Add to Collections</h3>
          <p style={styles.subtitle}>
            Select collections where this product should appear
          </p>
        </div>
        <div style={styles.counter}>{selectedCollections.size}</div>
      </div>

      {/* Search */}
      <div style={styles.searchWrapper}>
        <span style={styles.searchIcon}>🔍</span>
        <input
          type="text"
          placeholder="Search collections..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={styles.searchInput}
        />
      </div>

      {/* List */}
      <div style={styles.list}>
        {filtered.length === 0 ? (
          <div style={styles.noResults}>
            No collections match “{searchQuery}”
          </div>
        ) : (
          filtered.map((col) => {
            const isSelected = selectedCollections.has(col.id)
            return (
              <div
                key={col.id}
                role="button"
                tabIndex={0}
                onClick={() => onToggle(col.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onToggle(col.id)
                  }
                }}
                style={{
                  ...styles.item,
                  background: isSelected
                    ? theme.colors.primaryLight
                    : 'transparent',
                  borderColor: isSelected
                    ? theme.colors.primary
                    : 'transparent',
                }}
              >
                <div
                  style={{
                    ...styles.checkbox,
                    background: isSelected
                      ? theme.colors.primary
                      : 'white',
                    borderColor: isSelected
                      ? theme.colors.primary
                      : theme.colors.border,
                  }}
                >
                  {isSelected && (
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 12 12"
                      fill="none"
                    >
                      <path
                        d="M2 6L5 9L10 3"
                        stroke="white"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </div>
                <div style={styles.itemContent}>
                  <span style={styles.itemTitle}>{col.title}</span>
                  <span style={styles.itemCount}>
                    {col.products_count}{' '}
                    {col.products_count === 1 ? 'product' : 'products'}
                  </span>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Actions */}
      <div style={styles.actions}>
        <button
          type="button"
          onClick={handleSelectAll}
          style={styles.actionBtn}
        >
          Select All
        </button>
        <button
          type="button"
          onClick={onClear}
          style={styles.actionBtn}
        >
          Clear
        </button>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            style={{ ...styles.actionBtn, marginLeft: 'auto' }}
          >
            🔄 Refresh
          </button>
        )}
      </div>
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
    alignItems: 'center',
    gap: '12px',
    marginBottom: '16px',
  },
  headerContent: {
    flex: 1,
  },
  iconBox: {
    width: '40px',
    height: '40px',
    borderRadius: theme.radii.md,
    background: 'linear-gradient(135deg, #e6f5f1 0%, #d1f0e5 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  icon: {
    fontSize: '20px',
  },
  title: {
    fontSize: '15px',
    fontWeight: '600',
    color: theme.colors.text,
    margin: '0 0 2px',
  },
  subtitle: {
    fontSize: '12px',
    color: theme.colors.textSecondary,
    margin: 0,
    lineHeight: '1.4',
  },
  counter: {
    minWidth: '28px',
    height: '28px',
    padding: '0 8px',
    borderRadius: theme.radii.full,
    background: theme.colors.gradientPrimary,
    color: 'white',
    fontSize: '13px',
    fontWeight: '700',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchWrapper: {
    position: 'relative',
    marginBottom: '12px',
  },
  searchIcon: {
    position: 'absolute',
    left: '12px',
    top: '50%',
    transform: 'translateY(-50%)',
    fontSize: '14px',
    pointerEvents: 'none',
  },
  searchInput: {
    width: '100%',
    padding: '10px 12px 10px 38px',
    border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radii.md,
    fontSize: '13px',
    outline: 'none',
    boxSizing: 'border-box',
    background: theme.colors.bgSubtle,
    transition: theme.transitions.fast,
    color: theme.colors.text,
  },
  list: {
    maxHeight: '240px',
    overflowY: 'auto',
    marginBottom: '12px',
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    padding: '10px 12px',
    borderRadius: theme.radii.md,
    cursor: 'pointer',
    transition: theme.transitions.fast,
    marginBottom: '4px',
    border: '2px solid transparent',
  },
  checkbox: {
    width: '20px',
    height: '20px',
    borderRadius: theme.radii.sm,
    border: '2px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: '12px',
    flexShrink: 0,
    transition: theme.transitions.fast,
  },
  itemContent: {
    flex: 1,
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '8px',
  },
  itemTitle: {
    fontSize: '13px',
    fontWeight: '500',
    color: theme.colors.text,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  itemCount: {
    fontSize: '11px',
    color: theme.colors.textSecondary,
    background: theme.colors.bgSubtle,
    padding: '2px 8px',
    borderRadius: theme.radii.full,
    flexShrink: 0,
    fontWeight: '500',
  },
  actions: {
    display: 'flex',
    gap: '8px',
    paddingTop: '12px',
    borderTop: `1px solid ${theme.colors.borderLight}`,
  },
  actionBtn: {
    fontSize: '12px',
    padding: '8px 14px',
    cursor: 'pointer',
    border: `1px solid ${theme.colors.border}`,
    background: 'white',
    borderRadius: theme.radii.md,
    color: theme.colors.text,
    fontWeight: '500',
    transition: theme.transitions.fast,
  },
  loadingBox: {
    padding: '24px',
    textAlign: 'center',
    color: theme.colors.textSecondary,
    fontSize: '13px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '12px',
  },
  spinner: {
    width: '24px',
    height: '24px',
    border: `3px solid ${theme.colors.border}`,
    borderTopColor: theme.colors.primary,
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  emptyBox: {
    padding: '32px 24px',
    textAlign: 'center',
    background: theme.colors.bgSubtle,
    borderRadius: theme.radii.md,
    border: `1px dashed ${theme.colors.border}`,
  },
  emptyIcon: {
    fontSize: '32px',
    display: 'block',
    marginBottom: '8px',
  },
  emptyText: {
    fontSize: '13px',
    color: theme.colors.textSecondary,
    margin: '0 0 12px',
  },
  refreshBtn: {
    fontSize: '12px',
    padding: '8px 16px',
    background: theme.colors.gradientPrimary,
    color: 'white',
    border: 'none',
    borderRadius: theme.radii.md,
    cursor: 'pointer',
    fontWeight: '500',
  },
  noResults: {
    padding: '24px',
    textAlign: 'center',
    color: theme.colors.textMuted,
    fontSize: '13px',
  },
}