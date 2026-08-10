'use client';
import React from 'react';

export default function Footer() {
  return (
    <footer className="sdui-footer" style={{
      textAlign: 'center',
      padding: '1rem',
      background: 'var(--card-bg, rgba(255, 255, 255, 0.02))',
      borderTop: '1px solid rgba(255, 255, 255, 0.05)',
      borderRadius: 'var(--border-radius)',
      marginTop: '1rem',
      color: 'var(--text-color)', opacity: 0.4,
      fontSize: '0.75rem',
      fontFamily: 'var(--font-family)'
    }}>
      <div>VibeCloud SaaS &copy; 2026. Todos los derechos reservados.</div>
      <div style={{ fontSize: '0.65rem', marginTop: '0.2rem', opacity: 0.7 }}>
        Diseño adaptativo Server-Driven UI potenciado por <span style={{ color: 'var(--primary-color)', fontWeight: 'bold' }}>Gemini 2.0 Flash</span>
      </div>
    </footer>
  );
}
