export const palettes = [
  { id: 'minimal-light', name: 'Minimal Light', bg: '#f8fafc', text: '#0f172a', primary: '#4f46e5', secondary: '#10b981', cardBg: '#ffffff', border: '#e2e8f0', shadow: '0 4px 6px -1px rgba(0,0,0,0.1)' },
  { id: 'vibrant-glass', name: 'Vibrant Glass', bg: '#0f172a', text: '#ffffff', primary: '#ec4899', secondary: '#8b5cf6', cardBg: 'var(--card-bg, rgba(255, 255, 255, 0.05))', border: 'var(--border-color, rgba(255, 255, 255, 0.1))', shadow: '0 8px 32px 0 rgba(31, 38, 135, 0.37)' },
  { id: 'corporate-blue', name: 'Corporate Blue', bg: '#f0f4f8', text: '#102a43', primary: '#1864ab', secondary: '#0b7285', cardBg: '#ffffff', border: '#d9e2ec', shadow: '0 2px 4px rgba(0,0,0,0.05)' },
  { id: 'cyberpunk-neon', name: 'Cyberpunk Neon', bg: '#09090b', text: '#e2e8f0', primary: '#00ff9f', secondary: '#00b8ff', cardBg: '#18181b', border: '#00ff9f', shadow: '0 0 10px rgba(0, 255, 159, 0.5)' },
  { id: 'luxury-gold', name: 'Luxury Gold', bg: '#121212', text: '#fcfcfc', primary: '#d4af37', secondary: '#b8860b', cardBg: '#1e1e1e', border: '#333333', shadow: '0 4px 12px rgba(212, 175, 55, 0.15)' },
  { id: 'pastel-dream', name: 'Pastel Dream', bg: '#fdf4f6', text: '#4a4a4a', primary: '#f472b6', secondary: '#34d399', cardBg: '#ffffff', border: '#fce7f3', shadow: '0 4px 14px rgba(244, 114, 182, 0.15)' },
  { id: 'earth-tones', name: 'Earth Tones', bg: '#fcf9f2', text: '#3e2723', primary: '#8d6e63', secondary: '#d84315', cardBg: '#ffffff', border: '#efebe1', shadow: '0 2px 8px rgba(141, 110, 99, 0.1)' },
  { id: 'dark-elegance', name: 'Dark Elegance', bg: '#1c1c1e', text: '#f5f5f7', primary: '#0a84ff', secondary: '#30d158', cardBg: '#2c2c2e', border: '#3a3a3c', shadow: '0 8px 24px rgba(0,0,0,0.4)' },
  { id: 'sunset-glow', name: 'Sunset Glow', bg: '#fff5f5', text: '#2d3748', primary: '#ed8936', secondary: '#e53e3e', cardBg: '#ffffff', border: '#fed7d7', shadow: '0 4px 12px rgba(237, 137, 54, 0.2)' },
  { id: 'ocean-breeze', name: 'Ocean Breeze', bg: '#e0f2fe', text: '#0c4a6e', primary: '#0284c7', secondary: '#0d9488', cardBg: '#ffffff', border: '#bae6fd', shadow: '0 4px 6px rgba(2, 132, 199, 0.1)' }
];

export const headerVariants = [
  { id: 'header-standard', layout: 'flex justify-between items-center p-4', height: '60px' },
  { id: 'header-centered', layout: 'flex flex-col items-center justify-center p-4', height: '80px' },
  { id: 'header-minimal', layout: 'flex justify-end items-center p-2', height: '50px' }
];

export const heroVariants = [
  { id: 'hero-split', layout: 'grid grid-cols-2 gap-4 items-center', padding: '4rem 2rem' },
  { id: 'hero-centered', layout: 'flex flex-col items-center text-center', padding: '6rem 2rem' },
  { id: 'hero-banner', layout: 'relative w-full h-64 flex items-center justify-center', padding: '0' }
];

export const footerVariants = [
  { id: 'footer-simple', layout: 'text-center p-4', columns: 1 },
  { id: 'footer-multi', layout: 'grid grid-cols-4 gap-4 p-8', columns: 4 }
];

export const cardVariants = [
  { id: 'card-rounded', borderRadius: '16px', padding: '1.5rem', hoverScale: '1.02' },
  { id: 'card-sharp', borderRadius: '0px', padding: '1rem', hoverScale: '1.05' },
  { id: 'card-soft', borderRadius: '8px', padding: '1.25rem', hoverScale: '1.01' }
];

export const predefinedCombinations = [
  { id: 'combo-1', name: 'Minimal Light', palette: 'minimal-light', header: 'header-standard', hero: 'hero-split', footer: 'footer-multi', card: 'card-soft' },
  { id: 'combo-2', name: 'Vibrant Glass', palette: 'vibrant-glass', header: 'header-centered', hero: 'hero-centered', footer: 'footer-simple', card: 'card-rounded' },
  { id: 'combo-3', name: 'Corporate Blue', palette: 'corporate-blue', header: 'header-standard', hero: 'hero-split', footer: 'footer-multi', card: 'card-sharp' },
  { id: 'combo-4', name: 'Cyberpunk Neon', palette: 'cyberpunk-neon', header: 'header-minimal', hero: 'hero-banner', footer: 'footer-simple', card: 'card-sharp' },
  { id: 'combo-5', name: 'Luxury Gold', palette: 'luxury-gold', header: 'header-centered', hero: 'hero-split', footer: 'footer-multi', card: 'card-rounded' },
  { id: 'combo-6', name: 'Pastel Dream', palette: 'pastel-dream', header: 'header-standard', hero: 'hero-centered', footer: 'footer-simple', card: 'card-soft' }
  // You can add up to 20 curated combinations here
];

export const composeTheme = (paletteId, headerId, heroId, footerId, cardId) => {
  const p = palettes.find(x => x.id === paletteId) || palettes[0];
  const h = headerVariants.find(x => x.id === headerId) || headerVariants[0];
  const hr = heroVariants.find(x => x.id === heroId) || heroVariants[0];
  const f = footerVariants.find(x => x.id === footerId) || footerVariants[0];
  const c = cardVariants.find(x => x.id === cardId) || cardVariants[0];

  return {
    ...p,
    headerLayout: h.layout,
    headerHeight: h.height,
    heroLayout: hr.layout,
    heroPadding: hr.padding,
    footerLayout: f.layout,
    cardBorderRadius: c.borderRadius,
    cardPadding: c.padding,
    cardHoverScale: c.hoverScale
  };
};

export const applyThemeToDOM = (composedTheme) => {
  const root = document.documentElement;
  root.style.setProperty('--bg-color', composedTheme.bg);
  root.style.setProperty('--text-color', composedTheme.text);
  root.style.setProperty('--primary-color', composedTheme.primary);
  root.style.setProperty('--secondary-color', composedTheme.secondary);
  root.style.setProperty('--card-bg', composedTheme.cardBg);
  root.style.setProperty('--border-color', composedTheme.border);
  root.style.setProperty('--shadow-color', composedTheme.shadow);
  
  root.style.setProperty('--header-height', composedTheme.headerHeight);
  root.style.setProperty('--card-border-radius', composedTheme.cardBorderRadius);
  root.style.setProperty('--card-padding', composedTheme.cardPadding);
};
