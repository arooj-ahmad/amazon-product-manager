// src/components/CollectionsSelector.jsx
import { useState } from 'react'
import { theme } from '../styles/theme'

export default function CollectionsSelector({
  collections = [],
  selectedCollections = new Set(),
  loading = false,
  onToggle,
  onClear,
  onRefresh,   // ✅ NAYA
}) {
  const [searchQuery, setSearchQuery] = useState('')

  const filtered = collections.filter(col =>
    col.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleSelectAll = () => {
    filtered.forEach(col => {
      if (!selectedCollections.has(col.id)) {
        onToggle(col.id)
      }
    })
  }

  const handleClearAll = () => {
    onClear()
  }

  // Loading
  if (loading) {
    return (
      <div style={styles.section}>
        <div style={styles.label}>📁 Add to Collections</div>
        <div style={styles.loadingBox}>⏳ Loading collections...</div>
      </div>
    )
  }

  // Empty
  if (collections.length === 0) {
    return (
      <div style={styles.section}>
        <div style={styles.label}>📁 Add to Collections</div>
        <div style={styles.emptyBox}>
          No collections found.
          <br />
          <small style={{ color: theme.colors.textSecondary }}>
            Create collections in Shopify Admin first.
          </small>
        </div>
        {onRefresh && (
          <div style={styles.actions}>
            <button type="button" onClick={onRefresh} style={styles.actionBtn}>
              🔄 Refresh Collections
            </button>
          </div>
        )}
      </div>
    )
  }

  // Main
  return (
    <div style={styles.section}>
      <div style={styles.header}>
        <div style={styles.label}>📁 Add to Collections</div>
        <div style={styles.counter}>{selectedCollections.size} selected</div>
      </div>

      <input
        type="text"
        placeholder="🔍 Search collections..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        style={styles.searchInput}
      />

      <div style={styles.list}>
        {filtered.length === 0 ? (
          <div style={styles.noResults}>
            No collections match "{searchQuery}"
          </div>
        ) : (
          filtered.map(col => {
            const isSelected = selectedCollections.has(col.id)
            return (
              <div
                key={col.id}
                style={{
                  ...styles.item,
                  background: isSelected ? '#eefbf4' : 'transparent',
                }}
                onClick={() => onToggle(col.id)}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => onToggle(col.id)}
                  onClick={(e) => e.stopPropagation()}
                  style={styles.checkbox}
                />
                <div style={styles.itemContent}>
                  <span style={styles.itemTitle}>{col.title}</span>
                  <span style={styles.itemCount}>
                    {col.products_count} products
                  </span>
                </div>
              </div>
            )
          })
        )}
      </div>

      <div style={styles.actions}>
        <button type="button" onClick={handleSelectAll} style={styles.actionBtn}>
          Select All
        </button>
        <button type="button" onClick={handleClearAll} style={styles.actionBtn}>
          Clear All
        </button>
        {onRefresh && (   // ✅ NAYA
          <button type="button" onClick={onRefresh} style={styles.actionBtn}>
            🔄 Refresh
          </button>
        )}
      </div>
    </div>
  )
}

// Styles
const styles = {
  section: { marginTop: '20px', marginBottom: '16px' },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '10px',
  },
  label: { fontSize: '14px', fontWeight: '600', color: '#202223' },
  counter: { fontSize: '12px', color: '#008060', fontWeight: '600' },
  searchInput: {
    width: '100%',
    padding: '8px 12px',
    border: '1px solid #d9d9d9',
    borderRadius: '6px',
    fontSize: '13px',
    marginBottom: '8px',
    outline: 'none',
    boxSizing: 'border-box',
  },
  list: {
    maxHeight: '220px',
    overflowY: 'auto',
    border: '1px solid #e1e3e5',
    borderRadius: '8px',
    padding: '4px',
    background: '#fafbfc',
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    padding: '8px 10px',
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'background 0.15s',
    marginBottom: '2px',
  },
  checkbox: {
    marginRight: '10px',
    cursor: 'pointer',
    width: '16px',
    height: '16px',
    accentColor: '#008060',
  },
  itemContent: {
    flex: 1,
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  itemTitle: { fontSize: '13px', fontWeight: '500', color: '#202223' },
  itemCount: {
    fontSize: '11px',
    color: '#6d7175',
    background: '#f1f2f3',
    padding: '2px 8px',
    borderRadius: '10px',
  },
  noResults: {
    padding: '20px',
    textAlign: 'center',
    color: '#6d7175',
    fontSize: '13px',
  },
  loadingBox: {
    padding: '20px',
    textAlign: 'center',
    color: '#6d7175',
    fontSize: '13px',
    border: '1px solid #e1e3e5',
    borderRadius: '8px',
    background: '#fafbfc',
  },
  emptyBox: {
    padding: '16px',
    textAlign: 'center',
    color: '#6d7175',
    fontSize: '13px',
    border: '1px dashed #d9d9d9',
    borderRadius: '8px',
  },
  actions: { display: 'flex', gap: '8px', marginTop: '8px' },
  actionBtn: {
    fontSize: '12px',
    padding: '6px 12px',
    cursor: 'pointer',
    border: '1px solid #d9d9d9',
    background: 'white',
    borderRadius: '4px',
    color: '#202223',
    fontWeight: '500',
  },
}