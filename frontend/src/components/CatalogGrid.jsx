'use client';
import React from 'react';

export default function CatalogGrid({ products, page, pages, total, onPageChange, onAddToCart }) {
  return (
    <div className="sdui-catalog" style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '1rem',
      height: '100%'
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        color: 'var(--text-color, #fff)',
        fontFamily: 'var(--font-family)'
      }}>
        <h2 style={{ margin: 0, fontSize: '1.2rem', fontWeight: '600' }}>Catálogo de Productos</h2>
        <span style={{ fontSize: '0.8rem', opacity: 0.6 }}>Total: {total} artículos</span>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: '1rem',
        overflowY: 'auto',
        maxHeight: '400px',
        paddingRight: '0.5rem'
      }}>
        {products.length === 0 ? (
          <div style={{
            gridColumn: '1 / -1',
            textAlign: 'center',
            padding: '3rem',
            color: 'var(--text-color)', opacity: 0.4,
            background: 'var(--card-bg, rgba(255, 255, 255, 0.02))',
            borderRadius: 'var(--border-radius)',
            border: '1px dashed rgba(255, 255, 255, 0.1)',
            fontFamily: 'var(--font-family)'
          }}>
            No se encontraron productos.
          </div>
        ) : (
          products.map((product) => (
            <div
              key={product.id}
              style={{
                background: 'var(--card-bg, rgba(255, 255, 255, 0.03))',
                border: '1px solid rgba(255, 255, 255, 0.05)',
                borderRadius: 'var(--border-radius)',
                padding: '1rem',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                gap: '0.5rem',
                color: 'var(--text-color, #fff)',
                fontFamily: 'var(--font-family)',
                transition: 'transform 0.2s, border-color 0.2s'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.borderColor = 'var(--border-color, rgba(255, 255, 255, 0.15))';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.borderColor = 'var(--card-bg, rgba(255, 255, 255, 0.05))';
              }}
            >
              <div>
                <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', opacity: 0.5, letterSpacing: '0.05em' }}>
                  {product.category || 'Sin Categoría'}
                </span>
                <h3 style={{ margin: '0.2rem 0', fontSize: '0.95rem', fontWeight: '600', lineBreak: 'anywhere' }}>
                  {product.name}
                </h3>
                <p style={{ margin: 0, fontSize: '0.75rem', opacity: 0.6 }}>
                  Cód: {product.barcode}
                </p>
                <div style={{ margin: '0.5rem 0', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                    <span>Minorista:</span>
                    <strong style={{ color: 'var(--secondary-color)' }}>${product.price_retail ?? product.price}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                    <span>Mayorista:</span>
                    <strong style={{ color: 'var(--primary-color)' }}>${product.price_bulk ?? product.price}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', opacity: 0.6, marginTop: '0.25rem' }}>
                    <span>Stock Disp:</span>
                    <span>{product.stock_quantity} unidades</span>
                  </div>
                </div>
              </div>

              <button
                onClick={() => onAddToCart(product)}
                disabled={product.stock_quantity <= 0}
                style={{
                  background: product.stock_quantity > 0 ? 'var(--primary-color)' : 'var(--card-bg, rgba(255, 255, 255, 0.05))',
                  color: product.stock_quantity > 0 ? '#fff' : 'rgba(255, 255, 255, 0.3)',
                  border: 'none',
                  padding: '0.5rem',
                  borderRadius: 'calc(var(--border-radius) / 2)',
                  cursor: product.stock_quantity > 0 ? 'pointer' : 'not-allowed',
                  fontWeight: '600',
                  fontSize: '0.85rem',
                  transition: 'opacity 0.2s'
                }}
                onMouseEnter={(e) => {
                  if (product.stock_quantity > 0) e.target.style.opacity = 0.9;
                }}
                onMouseLeave={(e) => {
                  if (product.stock_quantity > 0) e.target.style.opacity = 1;
                }}
              >
                {product.stock_quantity > 0 ? 'Agregar al Carrito' : 'Sin Stock'}
              </button>
            </div>
          ))
        )}
      </div>

      {pages > 1 && (
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          gap: '1rem',
          marginTop: '0.5rem',
          fontFamily: 'var(--font-family)',
          color: 'var(--text-color, #fff)'
        }}>
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page === 1}
            style={{
              background: 'var(--card-bg, rgba(255, 255, 255, 0.05))',
              color: 'var(--text-color, #fff)',
              border: 'none',
              padding: '0.4rem 0.8rem',
              borderRadius: '4px',
              cursor: page === 1 ? 'not-allowed' : 'pointer',
              opacity: page === 1 ? 0.5 : 1
            }}
          >
            Anterior
          </button>
          <span style={{ fontSize: '0.85rem' }}>Página {page} de {pages}</span>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page === pages}
            style={{
              background: 'var(--card-bg, rgba(255, 255, 255, 0.05))',
              color: 'var(--text-color, #fff)',
              border: 'none',
              padding: '0.4rem 0.8rem',
              borderRadius: '4px',
              cursor: page === pages ? 'not-allowed' : 'pointer',
              opacity: page === pages ? 0.5 : 1
            }}
          >
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
}
