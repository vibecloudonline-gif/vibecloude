"use client";
import React from "react";
import { useStore } from "../context/StoreContext";

export default function StorefrontFooter() {
  const { storeInfo } = useStore();

  return (
    <footer
      style={{
        background: "var(--card-bg, #111)",
        borderTop: "1px solid var(--border-color)",
        padding: "4rem 2rem 2rem 2rem",
        color: "var(--text-color)",
        marginTop: "4rem",
      }}
    >
      <div
        style={{
          maxWidth: "1300px",
          margin: "0 auto",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))",
          gap: "3rem",
          marginBottom: "3rem",
        }}
      >
        {/* Brand */}
        <div>
          <h3 style={{ fontSize: "1.5rem", fontWeight: "800", marginBottom: "1rem" }}>
            {storeInfo.company_name || "VibeCloud Store"}
          </h3>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", lineHeight: "1.6" }}>
            Tienda minorista y mayorista oficial. Tecnología, indumentaria y lifestyle con envíos a todo el país y atención preferencial.
          </p>
        </div>

        {/* Links */}
        <div>
          <h4 style={{ fontSize: "1.1rem", fontWeight: "700", marginBottom: "1rem" }}>Navegación</h4>
          <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.9rem" }}>
            <li><a href="#inicio" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Inicio</a></li>
            <li><a href="#catalogo" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Catálogo</a></li>
            <li><a href="#ofertas" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Ofertas Mayoristas</a></li>
            <li><a href="https://vibecloud-backend.onrender.com/login" target="_blank" rel="noreferrer" style={{ color: "var(--primary-color)", textDecoration: "none", fontWeight: "600" }}>🔒 Acceso Empleados (POS)</a></li>
          </ul>
        </div>

        {/* Newsletter */}
        <div>
          <h4 style={{ fontSize: "1.1rem", fontWeight: "700", marginBottom: "1rem" }}>Novedades & Descuentos</h4>
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginBottom: "1rem" }}>
            Suscribite para recibir listas de precios mayoristas y ofertas exclusivas en tu email.
          </p>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <input
              type="email"
              placeholder="tu@email.com"
              style={{
                padding: "0.6rem 1rem",
                borderRadius: "8px",
                border: "1px solid var(--border-color)",
                background: "var(--bg-color)",
                color: "var(--text-color)",
                flex: 1,
                fontSize: "0.85rem",
              }}
            />
            <button className="btn-primary" style={{ padding: "0.6rem 1rem", fontSize: "0.85rem" }}>
              Suscribir
            </button>
          </div>
        </div>
      </div>

      <div
        style={{
          borderTop: "1px solid var(--border-color)",
          paddingTop: "2rem",
          textAlign: "center",
          fontSize: "0.8rem",
          color: "var(--text-muted)",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "1rem",
          maxWidth: "1300px",
          margin: "0 auto",
        }}
      >
        <span>© {new Date().getFullYear()} {storeInfo.company_name || "VibeCloud Store"}. Todos los derechos reservados.</span>
        <span>⚡ Powered by <strong>VibeCloud Enterprise SaaS</strong> • E-Commerce & POS</span>
      </div>
    </footer>
  );
}
