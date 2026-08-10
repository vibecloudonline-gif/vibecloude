"use client";
import React from "react";
import { useStore } from "../context/StoreContext";

export default function StorefrontCartModal() {
  const { cart, isCartOpen, setIsCartOpen, removeFromCart, updateQuantity, clearCart, getCartTotal, storeInfo } = useStore();

  if (!isCartOpen) return null;

  const handleWhatsAppCheckout = () => {
    if (cart.length === 0) return;
    const phone = "5491123456789"; // Default / store phone
    let message = `¡Hola *${storeInfo.company_name || "VibeCloud"}*! Quiero realizar un pedido desde la tienda online:\n\n`;
    
    cart.forEach((item, index) => {
      const price = item.price_retail ?? item.price ?? 0;
      message += `${index + 1}. *${item.name}* (x${item.quantity}) - $${(price * item.quantity).toLocaleString("es-AR")}\n`;
    });

    message += `\n*TOTAL DEL PEDIDO: $${getCartTotal().toLocaleString("es-AR")}*\n\nPor favor indíquenme cómo coordinar el pago y envío. ¡Muchas gracias!`;

    const encoded = encodeURIComponent(message);
    window.open(`https://api.whatsapp.com/send?phone=${phone}&text=${encoded}`, "_blank");
  };

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100vw",
        height: "100vh",
        background: "rgba(0, 0, 0, 0.6)",
        backdropFilter: "blur(6px)",
        zIndex: 1000,
        display: "flex",
        justifyContent: "flex-end",
      }}
      onClick={() => setIsCartOpen(false)}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "450px",
          height: "100vh",
          background: "var(--card-bg, #fff)",
          color: "var(--text-color)",
          boxShadow: "-10px 0 40px rgba(0,0,0,0.3)",
          display: "flex",
          flexDirection: "column",
          padding: "2rem",
          position: "relative",
          overflowY: "auto",
          borderLeft: "1px solid var(--border-color)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-color)", paddingBottom: "1.2rem", marginBottom: "1.5rem" }}>
          <h3 style={{ fontSize: "1.5rem", fontWeight: "800", margin: 0 }}>🛒 Tu Carrito ({cart.length})</h3>
          <button
            onClick={() => setIsCartOpen(false)}
            style={{
              background: "transparent",
              border: "none",
              fontSize: "1.5rem",
              color: "var(--text-color)",
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>

        {/* Cart Items List */}
        <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "1rem" }}>
          {cart.length === 0 ? (
            <div style={{ textAlign: "center", padding: "4rem 1rem", color: "var(--text-muted)" }}>
              <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>🛍️</div>
              <p style={{ fontSize: "1.1rem" }}>Tu carrito está vacío.</p>
              <p style={{ fontSize: "0.9rem", marginTop: "0.5rem" }}>¡Agregá productos desde el catálogo para empezar!</p>
            </div>
          ) : (
            cart.map((item) => {
              const price = item.price_retail ?? item.price ?? 0;
              return (
                <div
                  key={item.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "1rem",
                    borderRadius: "12px",
                    background: "rgba(0,0,0,0.03)",
                    border: "1px solid var(--border-color)",
                  }}
                >
                  <div style={{ flex: 1, paddingRight: "1rem" }}>
                    <h4 style={{ fontSize: "0.95rem", fontWeight: "700", marginBottom: "0.2rem" }}>{item.name}</h4>
                    <p style={{ fontSize: "0.85rem", color: "var(--primary-color)", fontWeight: "600" }}>
                      ${Number(price).toLocaleString("es-AR")} c/u
                    </p>
                  </div>

                  {/* Quantity Controls */}
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <button
                      onClick={() => updateQuantity(item.id, item.quantity - 1)}
                      style={{
                        width: "28px",
                        height: "28px",
                        borderRadius: "6px",
                        border: "1px solid var(--border-color)",
                        background: "var(--card-bg)",
                        color: "var(--text-color)",
                        fontWeight: "bold",
                        cursor: "pointer",
                      }}
                    >
                      -
                    </button>
                    <span style={{ fontWeight: "700", width: "20px", textAlign: "center", fontSize: "0.95rem" }}>{item.quantity}</span>
                    <button
                      onClick={() => updateQuantity(item.id, item.quantity + 1)}
                      style={{
                        width: "28px",
                        height: "28px",
                        borderRadius: "6px",
                        border: "1px solid var(--border-color)",
                        background: "var(--card-bg)",
                        color: "var(--text-color)",
                        fontWeight: "bold",
                        cursor: "pointer",
                      }}
                    >
                      +
                    </button>
                    <button
                      onClick={() => removeFromCart(item.id)}
                      style={{
                        background: "transparent",
                        border: "none",
                        color: "#ef4444",
                        marginLeft: "0.5rem",
                        cursor: "pointer",
                        fontSize: "1.1rem",
                      }}
                      title="Quitar producto"
                    >
                      🗑️
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer / Summary */}
        {cart.length > 0 && (
          <div style={{ borderTop: "2px solid var(--border-color)", paddingTop: "1.5rem", marginTop: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
              <span style={{ fontSize: "1.1rem", fontWeight: "600" }}>Total a Pagar:</span>
              <span style={{ fontSize: "1.8rem", fontWeight: "900", color: "var(--secondary-color)" }}>
                ${getCartTotal().toLocaleString("es-AR")}
              </span>
            </div>

            <button
              onClick={handleWhatsAppCheckout}
              className="btn-secondary"
              style={{
                width: "100%",
                padding: "1rem",
                fontSize: "1.1rem",
                fontWeight: "800",
                background: "#25D366",
                color: "#fff",
                border: "none",
                borderRadius: "12px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.5rem",
                boxShadow: "0 4px 15px rgba(37, 211, 102, 0.3)",
              }}
            >
              <span>📲 Pedir por WhatsApp</span>
            </button>

            <button
              onClick={clearCart}
              style={{
                width: "100%",
                background: "transparent",
                border: "none",
                color: "var(--text-muted)",
                fontSize: "0.85rem",
                marginTop: "1rem",
                cursor: "pointer",
                textDecoration: "underline",
              }}
            >
              Vaciar Carrito
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
