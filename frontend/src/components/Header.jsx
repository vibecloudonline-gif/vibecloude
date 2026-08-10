'use client';
import React, { useCallback, useEffect, useState } from 'react';
import { predefinedCombinations, composeTheme, applyThemeToDOM } from '../lib/themes';

export default function Header({ user, onLogout }) {
  const [activeTheme, setActiveTheme] = useState(() => {
    if (typeof window === 'undefined') return 'combo-1';
    return localStorage.getItem('vibecloud_theme') || 'combo-1';
  });

  useEffect(() => {
    const combo = predefinedCombinations.find(c => c.id === activeTheme) || predefinedCombinations[0];
    const composed = composeTheme(combo.palette, combo.header, combo.hero, combo.footer, combo.card);
    applyThemeToDOM(composed);
  }, [activeTheme]);

  const handleThemeChange = useCallback(async (comboId, saveToBackend = true) => {
    setActiveTheme(comboId);
    localStorage.setItem('vibecloud_theme', comboId);

    if (saveToBackend && user?.tenant_id) {
      try {
        await fetch('/api/store/theme', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ theme_id: comboId })
        });
      } catch (err) {
        console.error('Failed to save theme to backend', err);
      }
    }
  }, [user?.tenant_id]);

  return (
    <header className="sdui-header" style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '0 1.5rem',
      height: 'var(--header-height, 60px)',
      background: 'var(--card-bg, rgba(255, 255, 255, 0.05))',
      backdropFilter: 'blur(10px)',
      borderBottom: '1px solid var(--border-color, rgba(255, 255, 255, 0.1))',
      color: 'var(--text-color, #fff)',
      transition: 'all 0.3s ease'
    }}>
      <div>
        <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: '700', fontFamily: 'var(--font-family)' }}>
          VibeCloud <span style={{ color: 'var(--primary-color)' }}>Minorista</span>
        </h1>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
        
        {/* Admin Links */}
        {(user?.role === 'admin' || user?.role === 'superadmin') && (
          <a href="/admin/templates" style={{
            fontSize: '0.85rem',
            color: 'var(--text-color, #fff)',
            textDecoration: 'none',
            padding: '0.4rem 0.8rem',
            background: 'var(--primary-color, rgba(255,255,255,0.1))',
            borderRadius: '4px',
            fontWeight: '600'
          }}>
            Administrar Diseño
          </a>
        )}

        <div style={{ textAlign: 'right' }}>
          <div style={{ fontWeight: '600', fontSize: '0.9rem' }}>{user?.full_name || user?.username}</div>
        </div>

        <button
          onClick={onLogout}
          style={{
            background: 'var(--card-bg)',
            color: 'var(--text-color)',
            border: '1px solid var(--border-color)',
            padding: '0.4rem 0.8rem',
            borderRadius: '4px',
            cursor: 'pointer',
            fontWeight: '600',
            fontSize: '0.8rem',
            transition: 'all 0.2s'
          }}
          onMouseEnter={(e) => e.target.style.borderColor = 'var(--primary-color)'}
          onMouseLeave={(e) => e.target.style.borderColor = 'var(--border-color)'}
        >
          Cerrar
        </button>
      </div>
    </header>
  );
}
