'use client';
import { useEffect } from 'react';

export default function ThemeInjector({ theme }) {
  useEffect(() => {
    if (!theme) return;

    const root = document.documentElement;
    
    // Set custom properties
    if (theme.primary_color) {
      root.style.setProperty('--primary-color', theme.primary_color);
    }
    if (theme.secondary_color) {
      root.style.setProperty('--secondary-color', theme.secondary_color);
    }
    if (theme.background_gradient) {
      root.style.setProperty('--background-gradient', theme.background_gradient);
    }
    if (theme.border_radius) {
      root.style.setProperty('--border-radius', theme.border_radius);
    }
    if (theme.font_family) {
      // Clean quotes
      const cleanFont = theme.font_family.replace(/['"]/g, '');
      root.style.setProperty('--font-family', `"${cleanFont}", sans-serif`);

      // Load Google Font dynamically
      const linkId = 'dynamic-google-font';
      let link = document.getElementById(linkId);
      if (!link) {
        link = document.createElement('link');
        link.id = linkId;
        link.rel = 'stylesheet';
        document.head.appendChild(link);
      }
      link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(cleanFont)}:wght@300;400;600;700&display=swap`;
    }
  }, [theme]);

  return null; // Side effect only
}
