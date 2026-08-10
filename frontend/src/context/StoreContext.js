"use client";
import React, { createContext, useContext, useState, useEffect } from "react";

const StoreContext = createContext();

export const useStore = () => useContext(StoreContext);

const BACKEND_URL = process.env.NEXT_PUBLIC_VIBECLOUD_URL || "https://vibecloud-backend.onrender.com";

export const StoreProvider = ({ children }) => {
  const [storeInfo, setStoreInfo] = useState({
    company_name: "VibeCloud Store",
    logo_url: "/static/images/berelk_logo.png",
    storefront_template: "elegante",
  });
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cart, setCart] = useState(() => {
    if (typeof window === 'undefined') return [];
    try {
      const savedCart = localStorage.getItem("vibecloud_cart");
      return savedCart ? JSON.parse(savedCart) : [];
    } catch (e) {
      console.error("Error loading cart:", e);
      return [];
    }
  });
  const [isCartOpen, setIsCartOpen] = useState(false);

  // Save cart to localStorage
  useEffect(() => {
    try {
      localStorage.setItem("vibecloud_cart", JSON.stringify(cart));
    } catch (e) {
      console.error("Error saving cart:", e);
    }
  }, [cart]);

  // Fetch store info & catalog from backend
  useEffect(() => {
    const fetchStoreData = async () => {
      try {
        setLoading(true);
        // Fetch Store Info
        const infoRes = await fetch(`${BACKEND_URL}/api/v1/store/public-info`);
        if (infoRes.ok) {
          const infoData = await infoRes.json();
          setStoreInfo(infoData);
          if (typeof document !== "undefined") {
            document.body.className = `theme-${infoData.storefront_template || "elegante"}`;
          }
        }

        // Fetch Products
        const prodRes = await fetch(`${BACKEND_URL}/api/v1/store/public-catalog`);
        if (prodRes.ok) {
          const prodData = await prodRes.json();
          setProducts(prodData.items || []);
        }
      } catch (err) {
        console.error("Error loading storefront data from backend:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchStoreData();
  }, []);

  // Cart actions
  const addToCart = (product, quantity = 1) => {
    setCart((prev) => {
      const existing = prev.find((item) => item.id === product.id);
      if (existing) {
        return prev.map((item) =>
          item.id === product.id ? { ...item, quantity: item.quantity + quantity } : item
        );
      }
      return [...prev, { ...product, quantity }];
    });
    setIsCartOpen(true);
  };

  const removeFromCart = (productId) => {
    setCart((prev) => prev.filter((item) => item.id !== productId));
  };

  const updateQuantity = (productId, quantity) => {
    if (quantity <= 0) {
      removeFromCart(productId);
      return;
    }
    setCart((prev) =>
      prev.map((item) => (item.id === productId ? { ...item, quantity } : item))
    );
  };

  const clearCart = () => {
    setCart([]);
  };

  const getCartTotal = () => {
    return cart.reduce((total, item) => total + (item.price || 0) * item.quantity, 0);
  };

  const getCartCount = () => {
    return cart.reduce((count, item) => count + item.quantity, 0);
  };

  return (
    <StoreContext.Provider
      value={{
        storeInfo,
        products,
        loading,
        cart,
        isCartOpen,
        setIsCartOpen,
        addToCart,
        removeFromCart,
        updateQuantity,
        clearCart,
        getCartTotal,
        getCartCount,
        BACKEND_URL,
      }}
    >
      {children}
    </StoreContext.Provider>
  );
};
