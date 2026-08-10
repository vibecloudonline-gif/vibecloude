'use client';
import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { predefinedCombinations, composeTheme, applyThemeToDOM } from '@/lib/themes';
import { apiRequest } from '@/services/api';

export default function TemplatesAdmin() {
  const router = useRouter();
  const [activeTheme, setActiveTheme] = useState(() => {
    if (typeof window === 'undefined') return 'combo-1';
    return localStorage.getItem('vibecloud_theme') || 'combo-1';
  });
  const [saving, setSaving] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [generating, setGenerating] = useState(false);

  const handlePreview = (comboId) => {
    setActiveTheme(comboId);
    const combo = predefinedCombinations.find(c => c.id === comboId);
    if (combo) {
      const composed = composeTheme(combo.palette, combo.header, combo.hero, combo.footer, combo.card);
      applyThemeToDOM(composed);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await apiRequest('/store/theme', {
        method: 'PUT',
        body: { theme_id: activeTheme }
      });
      localStorage.setItem('vibecloud_theme', activeTheme);
      alert('Tema guardado con éxito.');
    } catch (err) {
      alert('Error al guardar el tema: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateAI = async () => {
    if (!aiPrompt.trim()) return;
    setGenerating(true);
    try {
      const res = await apiRequest('/ai/theme', {
        method: 'POST',
        body: { prompt: aiPrompt }
      });
      // Assuming response gives us a composed theme or a theme ID
      if (res && res.theme) {
        applyThemeToDOM(res.theme);
        alert('Tema generado y aplicado a la vista previa. Haz clic en "Guardar Tema Actual" para confirmar.');
      } else {
        alert('No se pudo generar el tema.');
      }
    } catch (err) {
      alert('Error generando tema con IA: ' + err.message);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto', color: 'var(--text-color, #fff)' }}>
      <button onClick={() => router.push('/')} style={{ marginBottom: '1rem', background: 'transparent', border: '1px solid var(--border-color)', color: 'var(--text-color)', padding: '0.5rem 1rem', borderRadius: '4px', cursor: 'pointer' }}>
        &larr; Volver al Dashboard
      </button>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2rem', margin: 0 }}>Administrador de Plantillas</h1>
        <button 
          onClick={handleSave} 
          disabled={saving}
          style={{
            background: 'var(--primary-color, #4F46E5)',
            color: '#fff',
            border: 'none',
            padding: '0.75rem 1.5rem',
            borderRadius: '6px',
            fontSize: '1rem',
            fontWeight: '600',
            cursor: saving ? 'not-allowed' : 'pointer',
            opacity: saving ? 0.7 : 1
          }}
        >
          {saving ? 'Guardando...' : 'Guardar Tema Actual'}
        </button>
      </div>

      <div style={{ background: 'var(--card-bg, rgba(255,255,255,0.05))', padding: '1.5rem', borderRadius: '12px', marginBottom: '2rem', border: '1px solid var(--border-color, rgba(255,255,255,0.1))' }}>
        <h2 style={{ marginTop: 0 }}>Generar con IA (Gemini)</h2>
        <p style={{ opacity: 0.8, fontSize: '0.9rem', marginBottom: '1rem' }}>
          Describe el estilo que quieres para tu tienda y la IA de VibeCloud generará una paleta y estructura única para ti.
        </p>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <input 
            type="text" 
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            placeholder="Ej: Tienda minimalista de ropa para bebés con tonos pastel y botones redondeados..."
            style={{
              flex: 1,
              padding: '0.75rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              background: 'rgba(0,0,0,0.2)',
              color: 'var(--text-color)',
              outline: 'none'
            }}
          />
          <button 
            onClick={handleGenerateAI}
            disabled={generating || !aiPrompt.trim()}
            style={{
              background: '#10B981',
              color: '#fff',
              border: 'none',
              padding: '0 1.5rem',
              borderRadius: '6px',
              fontWeight: '600',
              cursor: (generating || !aiPrompt.trim()) ? 'not-allowed' : 'pointer',
              opacity: (generating || !aiPrompt.trim()) ? 0.7 : 1
            }}
          >
            {generating ? 'Generando...' : 'Generar Magia ✨'}
          </button>
        </div>
      </div>

      <h2>Plantillas Predefinidas</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1.5rem', marginTop: '1.5rem' }}>
        {predefinedCombinations.map(combo => (
          <div 
            key={combo.id}
            onClick={() => handlePreview(combo.id)}
            style={{
              background: 'var(--card-bg, rgba(255,255,255,0.05))',
              border: activeTheme === combo.id ? '2px solid var(--primary-color)' : '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '1.5rem',
              cursor: 'pointer',
              transition: 'all 0.2s',
              opacity: activeTheme === combo.id ? 1 : 0.7
            }}
          >
            <h3 style={{ margin: '0 0 1rem 0' }}>{combo.name}</h3>
            <div style={{ fontSize: '0.85rem', opacity: 0.8, marginBottom: '0.5rem' }}>
              <strong>Paleta:</strong> {combo.palette}
            </div>
            <div style={{ fontSize: '0.85rem', opacity: 0.8, marginBottom: '0.5rem' }}>
              <strong>Cabecera:</strong> {combo.header}
            </div>
            <div style={{ fontSize: '0.85rem', opacity: 0.8 }}>
              <strong>Tarjetas:</strong> {combo.card}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
