import "./globals.css";
import { StoreProvider } from "../context/StoreContext";

export const metadata = {
  title: "VibeCloud SaaS POS Terminal & Tienda Online",
  description: "Terminal de Ventas Minorista y Tienda E-commerce Moderna",
};

export default function RootLayout({ children }) {
  return (
    <html lang="es">
      <body style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <StoreProvider>
          {children}
        </StoreProvider>
      </body>
    </html>
  );
}
