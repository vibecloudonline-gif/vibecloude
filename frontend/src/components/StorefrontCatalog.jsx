"use client";
import React, { useState } from "react";
import { useStore } from "../context/StoreContext";

const SAMPLE_PRODUCTS = [
  {
    id: 101,
    name: "Remera Oversize Heavyweight 280g",
    category: "Indumentaria",
    barcode: "STR-001",
    price: 18500,
    price_bulk: 14500,
    stock_quantity: 45,
    image_url: "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=500&auto=format&fit=crop&q=60&ixlib=rb-4.0.3",
  },
  {
    id: 102,
    name: "Auriculares Inalámbricos Studio Pro ANC",
    category: "Tecnología",
    barcode: "TEC-089",
    price: 85000,
    price_bulk: 72000,
    stock_quantity: 12,
    image_url: "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&auto=format&fit=crop&q=60&ixlib=rb-4.0.3",
  },
  {
    id: 103,
    name: "Perfume Orgánico Ámbar & Maderas 100ml",
    category: "Cuidado Personal",
    barcode: "NAT-304",
    price: 42000,
    price_bulk: 35000,
    stock_quantity: 28,
    image_url: "https://images.unsplash.com/photo-1547887537-6158d64c35e3?w=500&auto=format&fit=crop&q=60&ixlib=rb-4.0.3",
  },
  {
    id: 104,
    name: "Zapatillas Urban Retro Vintage 90s",
    category: "Calzado",
    barcode: "URB-552",
    price: 95000,
    price_bulk: 80000,
    stock_quantity: 8,
    image_url: "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500&auto=format&fit=crop&q=60&ixlib=rb-4.0.3",
  },
  {
    id: 105,
    name: "Reloj Inteligente Ultra Fit 49mm AMOLED",
    category: "Tecnología",
    barcode: "TEC-112",
    price: 64000,
    price_bulk: 55000,
    stock_quantity: 19,
    image_url: "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&auto=format&fit=crop&q=60&ixlib=rb-4.0.3",
  },
  {
    id: 106,
    name: "Mochila Impermeable Tech Commuter 25L",
    category: "Accesorios",
    barcode: "ACC-901",
    price: 48000,
    price_bulk: 39000,
    stock_quantity: 34,
    image_url: "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=500&auto=format&fit=crop&q=60&ixlib=rb-4.0.3",
  },
];

export default function StorefrontCatalog() {
  const { products, loading, addToCart, BACKEND_URL } = useStore();
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("TODOS");

  const displayProducts = products && products.length > 0 ? products : SAMPLE_PRODUCTS;

  const categories = ["TODOS", ...new Set(displayProducts.map((p) => p.category || "General"))];

  const filteredProducts = displayProducts.filter((product) => {
    const matchesSearch =
      product.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (product.barcode && product.barcode.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesCategory = selectedCategory === "TODOS" || (product.category || "General") === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  return (
    <section id="catalogo" style={{ padding: "4rem 2rem", maxWidth: "1300px", margin: "0 auto" }}>
      {/* Catalog Title & Filters */}
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: "1.5rem", marginBottom: "3rem" }}>
        <div>
          <h2 style={{ fontSize: "2.2rem", fontWeight: "800", marginBottom: "0.5rem" }}>Catálogo Destacado</h2>
          <p style={{ color: "var(--text-muted)", fontSize: "1rem" }}>
            Elegí los productos y agregalos a tu carrito. Descuentos automáticos al por mayor.
          </p>
        </div>

        {/* Search Bar */}
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
          <input
            type="text"
            placeholder="🔍 Buscar por nombre o código..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              padding: "0.75rem 1.2rem",
              borderRadius: "50px",
              border: "1px solid var(--border-color)",
              background: "var(--card-bg)",
              color: "var(--text-color)",
              width: "280px",
              fontSize: "0.95rem",
            }}
          />
        </div>
      </div>

      {/* Category Pills */}
      <div style={{ display: "flex", gap: "0.8rem", overflowX: "auto", paddingBottom: "1rem", marginBottom: "2.5rem" }}>
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            style={{
              padding: "0.6rem 1.4rem",
              borderRadius: "50px",
              border: selectedCategory === cat ? "none" : "1px solid var(--border-color)",
              background: selectedCategory === cat ? "var(--primary-color)" : "var(--card-bg)",
              color: selectedCategory === cat ? "#fff" : "var(--text-color)",
              fontWeight: "600",
              fontSize: "0.9rem",
              cursor: "pointer",
              whiteSpace: "nowrap",
              transition: "all 0.2s ease",
            }}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Products Grid */}
      {loading ? (
        <div style={{ textAlign: "center", padding: "5rem", color: "var(--text-muted)", fontSize: "1.2rem" }}>
          ⏳ Cargando catálogo de productos...
        </div>
      ) : filteredProducts.length === 0 ? (
        <div style={{ textAlign: "center", padding: "5rem", background: "var(--card-bg)", borderRadius: "var(--card-border-radius)", border: "1px dashed var(--border-color)" }}>
          <h3 style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>No encontramos productos 😕</h3>
          <p style={{ color: "var(--text-muted)" }}>Intentá buscar con otra palabra clave o elegí la categoría &quot;TODOS&quot;.</p>
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: "2rem",
          }}
        >
          {filteredProducts.map((product) => {
            const priceRetail = product.price_retail ?? product.price ?? 0;
            const priceBulk = product.price_bulk ?? (priceRetail * 0.85);
            const imageUrl = product.image_url
              ? product.image_url.startsWith("http")
                ? product.image_url
                : `${BACKEND_URL}${product.image_url}`
              : "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&auto=format&fit=crop&q=60&ixlib=rb-4.0.3";

            return (
              <div key={product.id} className="store-card" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
                {/* Product Image */}
                <div style={{ position: "relative", height: "240px", overflow: "hidden", background: "#111" }}>
                  <img
                    src={imageUrl}
                    alt={product.name}
                    style={{ width: "100%", height: "100%", objectFit: "cover", transition: "transform 0.4s ease" }}
                    onMouseEnter={(e) => (e.target.style.transform = "scale(1.08)")}
                    onMouseLeave={(e) => (e.target.style.transform = "scale(1)")}
                  />
                  <div
                    style={{
                      position: "absolute",
                      top: "12px",
                      left: "12px",
                      background: "rgba(0,0,0,0.6)",
                      backdropFilter: "blur(4px)",
                      color: "#fff",
                      padding: "0.3rem 0.8rem",
                      borderRadius: "50px",
                      fontSize: "0.75rem",
                      fontWeight: "700",
                      textTransform: "uppercase",
                    }}
                  >
                    {product.category || "General"}
                  </div>
                </div>

                {/* Product Details */}
                <div style={{ padding: "1.5rem", display: "flex", flexDirection: "column", flex: 1, justifyContent: "space-between" }}>
                  <div>
                    <h3 style={{ fontSize: "1.15rem", fontWeight: "700", marginBottom: "0.5rem", lineHeight: "1.3" }}>
                      {product.name}
                    </h3>
                    <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "1.2rem" }}>
                      Cód: {product.barcode || "N/A"} • Stock: {product.stock_quantity ?? "Disponible"}
                    </p>
                  </div>

                  <div>
                    {/* Prices */}
                    <div style={{ background: "rgba(0,0,0,0.04)", padding: "0.8rem", borderRadius: "10px", marginBottom: "1.2rem", border: "1px solid var(--border-color)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.3rem" }}>
                        <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Precio Unitario:</span>
                        <strong style={{ fontSize: "1.2rem", color: "var(--text-color)" }}>
                          ${Number(priceRetail).toLocaleString("es-AR")}
                        </strong>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: "0.85rem", color: "var(--primary-color)", fontWeight: "600" }}>Por Mayor (Bulto):</span>
                        <strong style={{ fontSize: "1.1rem", color: "var(--primary-color)" }}>
                          ${Number(priceBulk).toLocaleString("es-AR")}
                        </strong>
                      </div>
                    </div>

                    {/* Add to Cart Button */}
                    <button
                      onClick={() => addToCart(product, 1)}
                      className="btn-primary"
                      style={{ width: "100%", padding: "0.8rem", fontSize: "1rem" }}
                    >
                      <span>🛒 Agregar al Carrito</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
