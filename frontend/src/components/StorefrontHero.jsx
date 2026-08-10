"use client";
import React from "react";
import { useStore } from "../context/StoreContext";

export default function StorefrontHero() {
  const { storeInfo } = useStore();

  return (
    <section
      id="inicio"
      style={{
        position: "relative",
        padding: "5rem 2rem",
        textAlign: "center",
        overflow: "hidden",
        borderBottom: "1px solid var(--border-color)",
        background: "linear-gradient(180deg, var(--card-bg) 0%, var(--bg-color) 100%)",
      }}
    >
      <div style={{ maxWidth: "800px", margin: "0 auto", position: "relative", zIndex: 2 }}>
        <div
          style={{
            display: "inline-block",
            background: "rgba(79, 70, 229, 0.1)",
            color: "var(--primary-color)",
            padding: "0.4rem 1rem",
            borderRadius: "50px",
            fontSize: "0.85rem",
            fontWeight: "700",
            marginBottom: "1.5rem",
            border: "1px solid var(--primary-color)",
          }}
        >
          🚀 TIENDA OFICIAL DE {storeInfo.company_name?.toUpperCase() || "VIBECLOUD"}
        </div>

        <h2
          style={{
            fontSize: "3.5rem",
            fontWeight: "900",
            lineHeight: "1.1",
            marginBottom: "1.5rem",
            background: "linear-gradient(135deg, var(--text-color) 0%, var(--primary-color) 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Descubrí la Nueva Generación en E-Commerce
        </h2>

        <p
          style={{
            fontSize: "1.2rem",
            color: "var(--text-muted)",
            marginBottom: "2.5rem",
            lineHeight: "1.6",
            maxWidth: "650px",
            margin: "0 auto 2.5rem auto",
          }}
        >
          Calidad indiscutible, atención inmediata y envíos a todo el país. Explorá nuestro catálogo mayorista y minorista con precios exclusivos y checkout express.
        </p>

        <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
          <a href="#catalogo" className="btn-primary" style={{ textDecoration: "none", padding: "1rem 2rem", fontSize: "1.1rem" }}>
            Ver Catálogo Completo →
          </a>
          <a href="#ofertas" className="btn-outline" style={{ textDecoration: "none", padding: "1rem 2rem", fontSize: "1.1rem" }}>
            Descuentos por Bulto 🔥
          </a>
        </div>
      </div>

      {/* Decorative Glows */}
      <div
        style={{
          position: "absolute",
          top: "-50%",
          left: "50%",
          transform: "translateX(-50%)",
          width: "600px",
          height: "600px",
          background: "radial-gradient(circle, var(--primary-color) 0%, transparent 70%)",
          opacity: 0.15,
          filter: "blur(80px)",
          zIndex: 1,
          pointerEvents: "none",
        }}
      />
    </section>
  );
}
