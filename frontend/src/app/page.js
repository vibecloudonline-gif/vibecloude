"use client";
import React from "react";
import StorefrontHeader from "../components/StorefrontHeader";
import StorefrontHero from "../components/StorefrontHero";
import StorefrontCatalog from "../components/StorefrontCatalog";
import StorefrontCartModal from "../components/StorefrontCartModal";
import StorefrontFooter from "../components/StorefrontFooter";

export default function Home() {
  return (
    <main style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "var(--bg-color)" }}>
      <StorefrontHeader />
      <StorefrontHero />
      
      {/* Banner de Ofertas Destacadas */}
      <section id="ofertas" style={{ background: "var(--primary-color)", color: "#fff", padding: "1.5rem 2rem", textAlign: "center", fontWeight: "700", fontSize: "1.1rem" }}>
        🔥 ¡ENVÍO GRATIS en compras superiores a $100.000! Descuentos automáticos por bulto en todo el catálogo.
      </section>

      <StorefrontCatalog />
      <StorefrontCartModal />
      <StorefrontFooter />
    </main>
  );
}
