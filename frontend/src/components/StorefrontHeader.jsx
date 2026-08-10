"use client";
import React from "react";
import { useStore } from "../context/StoreContext";

export default function StorefrontHeader() {
  const { storeInfo, getCartCount, setIsCartOpen, BACKEND_URL } = useStore();

  const handleThemeChange = (e) => {
    const newTheme = e.target.value;
    document.body.className = `theme-${newTheme}`;
  };

  const currentTheme =
    typeof document !== "undefined" && document.body.className.replace("theme-", "")
      ? document.body.className.replace("theme-", "")
      : storeInfo.storefront_template || "elegante";

  return (
    <header
      style={{
        background: "var(--header-bg, #ffffff)",
        borderBottom: "1px solid var(--border-color)",
        padding: "1rem 2rem",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        position: "sticky",
        top: 0,
        zIndex: 100,
        backdropFilter: "blur(12px)",
        boxShadow: "0 2px 10px rgba(0,0,0,0.05)",
      }}
    >
      {/* Brand & Logo */}
      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        {storeInfo.logo_url && (
          <img
            src={storeInfo.logo_url.startsWith("http") ? storeInfo.logo_url : `${BACKEND_URL}${storeInfo.logo_url}`}
            alt={storeInfo.company_name}
            style={{ height: "40px", objectFit: "contain", borderRadius: "6px" }}
            onError={(e) => {
              e.target.style.display = "none";
            }}
          />
        )}
        <h1 style={{ fontSize: "1.5rem", fontWeight: "800", margin: 0, letterSpacing: "-0.5px" }}>
          {storeInfo.company_name || "VibeCloud Store"}
        </h1>
      </div>

      {/* Navigation Links */}
      <nav style={{ display: "flex", gap: "2rem", alignItems: "center", fontWeight: "600", fontSize: "0.95rem" }}>
        <a href="#inicio" style={{ color: "var(--text-color)", textDecoration: "none" }}>
          Inicio
        </a>
        <a href="#catalogo" style={{ color: "var(--text-color)", textDecoration: "none" }}>
          Catálogo
        </a>
        <a href="#ofertas" style={{ color: "var(--primary-color)", textDecoration: "none" }}>
          Ofertas ✨
        </a>
      </nav>

      {/* Actions: Theme Switcher & Cart */}
      <div style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
        {/* Template Selector Badge (User choice request) */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", background: "var(--card-bg)", padding: "0.4rem 0.8rem", borderRadius: "50px", border: "1px solid var(--border-color)", fontSize: "0.85rem" }}>
          <span style={{ opacity: 0.7 }}>🎨 Plantilla:</span>
          <select
            defaultValue={currentTheme}
            onChange={handleThemeChange}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--primary-color)",
              fontWeight: "700",
              cursor: "pointer",
              outline: "none",
              paddingRight: "1.5rem",
            }}
          >
            <option value="elegante">🩵 Elegante</option>
            <option value="urbano">🖤 Urbano</option>
            <option value="natural">🌿 Natural</option>
            <option value="tech">⚡ Tech</option>
          </select>
        </div>

        {/* Cart Button */}
        <button
          onClick={() => setIsCartOpen(true)}
          className="btn-primary"
          style={{ position: "relative", padding: "0.6rem 1.2rem", borderRadius: "50px" }}
        >
          <span>🛒 Carrito</span>
          {getCartCount() > 0 && (
            <span
              style={{
                background: "var(--secondary-color)",
                color: "#fff",
                borderRadius: "50%",
                padding: "0.15rem 0.5rem",
                fontSize: "0.75rem",
                fontWeight: "bold",
                marginLeft: "0.3rem",
              }}
            >
              {getCartCount()}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
