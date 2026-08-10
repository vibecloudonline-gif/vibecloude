"use client";
import { useEffect } from "react";

export default function Onboarding() {
  useEffect(() => {
    window.location.href = "https://vibecloud-backend.onrender.com/login";
  }, []);

  return (
    <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f1f5f9", color: "#333" }}>
      <h2>Redirigiendo al sistema...</h2>
    </div>
  );
}
