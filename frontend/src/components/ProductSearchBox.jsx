'use client';
import React from 'react';

export default function ProductSearchBox({ value, onChange, onSearch }) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      onSearch();
    }
  };

  return (
    <div className="sdui-searchbox" style={{
      padding: '1rem',
      background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
      backdropFilter: 'blur(5px)',
      border: '1px solid rgba(255, 255, 255, 0.05)',
      borderRadius: 'var(--border-radius)',
      marginBottom: '1rem',
      display: 'flex',
      gap: '1rem'
    }}>
      <input
        type="text"
        placeholder="Buscar por código de barras, nombre o N° artículo..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        style={{
          flex: 1,
          background: 'var(--card-bg, rgba(0, 0, 0, 0.2))',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          padding: '0.75rem 1rem',
          borderRadius: 'calc(var(--border-radius) / 2)',
          color: 'var(--text-color, #fff)',
          fontSize: '0.95rem',
          outline: 'none',
          fontFamily: 'var(--font-family)',
          transition: 'border-color 0.2s'
        }}
        onFocus={(e) => e.target.style.borderColor = 'var(--primary-color)'}
        onBlur={(e) => e.target.style.borderColor = 'var(--border-color, rgba(255, 255, 255, 0.1))'}
      />
      <button
        onClick={onSearch}
        style={{
          background: 'var(--primary-color)',
          color: 'var(--text-color, #fff)',
          border: 'none',
          padding: '0.75rem 1.5rem',
          borderRadius: 'calc(var(--border-radius) / 2)',
          cursor: 'pointer',
          fontWeight: '600',
          fontSize: '0.95rem',
          fontFamily: 'var(--font-family)',
          transition: 'opacity 0.2s'
        }}
        onMouseEnter={(e) => e.target.style.opacity = 0.9}
        onMouseLeave={(e) => e.target.style.opacity = 1}
      >
        Buscar
      </button>
    </div>
  );
}
