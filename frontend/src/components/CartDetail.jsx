'use client';
import React from 'react';

export default function CartDetail({ items, onUpdateQuantity, onUpdatePriceType, onRemoveItem, onClearCart }) {
  const calculateItemPrice = (item) => {
    const raw = item.price_type === 'bulk'
      ? (item.product.price_bulk ?? item.product.price)
      : (item.product.price_retail ?? item.product.price);
    return parseFloat(raw || 0);
  };

  const total = items.reduce((sum, item) => {
    return sum + (calculateItemPrice(item) * item.quantity);
  }, 0);

  return (
    <div className="sdui-cart" style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '1rem',
      height: '100%',
      background: 'var(--card-bg, rgba(255, 255, 255, 0.02))',
      border: '1px solid rgba(255, 255, 255, 0.05)',
      borderRadius: 'var(--border-radius)',
      padding: '1.2rem',
      color: 'var(--text-color, #fff)',
      fontFamily: 'var(--font-family)'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255, 255, 255, 0.1)', paddingBottom: '0.75rem' }}>
        <h2 style={{ margin: 0, fontSize: '1.2rem', fontWeight: '600' }}>Carrito de Ventas</h2>
        {items.length > 0 && (
          <button
            onClick={onClearCart}
            style={{
              background: 'transparent',
              color: 'var(--text-color)', opacity: 0.4,
              border: 'none',
              cursor: 'pointer',
              fontSize: '0.8rem',
              textDecoration: 'underline'
            }}
          >
            Vaciar
          </button>
        )}
      </div>

      <div style={{
        flex: 1,
        overflowY: 'auto',
        maxHeight: '300px',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        paddingRight: '0.25rem'
      }}>
        {items.length === 0 ? (
          <div style={{
            textAlign: 'center',
            padding: '3rem 1rem',
            color: 'var(--text-color)', opacity: 0.3,
            fontSize: '0.9rem'
          }}>
            El carrito está vacío. Agregá productos desde el catálogo.
          </div>
        ) : (
          items.map((item) => {
            const unitPrice = calculateItemPrice(item);
            const itemTotal = unitPrice * item.quantity;
            return (
              <div
                key={item.product.id}
                style={{
                  background: 'rgba(0,0,0,0.15)',
                  border: '1px solid rgba(255, 255, 255, 0.03)',
                  borderRadius: 'calc(var(--border-radius) / 2)',
                  padding: '0.75rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.5rem'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ maxWidth: '75%' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: '600', lineBreak: 'anywhere' }}>{item.product.name}</div>
                    <div style={{ fontSize: '0.75rem', opacity: 0.5 }}>Cód: {item.product.barcode}</div>
                  </div>
                  <button
                    onClick={() => onRemoveItem(item.product.id)}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: '#ef4444',
                      cursor: 'pointer',
                      fontSize: '0.8rem'
                    }}
                  >
                    Quitar
                  </button>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.25rem' }}>
                  {/* Price Type Selector */}
                  <select
                    value={item.price_type}
                    onChange={(e) => onUpdatePriceType(item.product.id, e.target.value)}
                    style={{
                      background: 'var(--card-bg, rgba(0, 0, 0, 0.3))',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      color: 'var(--text-color, #fff)',
                      fontSize: '0.75rem',
                      borderRadius: '4px',
                      padding: '0.2rem 0.4rem',
                      outline: 'none'
                    }}
                  >
                    <option value="retail">Minorista (${item.product.price_retail ?? item.product.price})</option>
                    <option value="bulk">Mayorista (${item.product.price_bulk ?? item.product.price})</option>
                  </select>

                  {/* Quantity Controls */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <button
                      onClick={() => onUpdateQuantity(item.product.id, item.quantity - 1)}
                      style={{
                        background: 'var(--card-bg, rgba(255, 255, 255, 0.05))',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        color: 'var(--text-color, #fff)',
                        width: '24px',
                        height: '24px',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 'bold'
                      }}
                    >
                      -
                    </button>
                    <span style={{ fontSize: '0.85rem', width: '20px', textAlign: 'center' }}>{item.quantity}</span>
                    <button
                      onClick={() => onUpdateQuantity(item.product.id, item.quantity + 1)}
                      disabled={item.quantity >= item.product.stock_quantity}
                      style={{
                        background: 'var(--card-bg, rgba(255, 255, 255, 0.05))',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        color: 'var(--text-color, #fff)',
                        width: '24px',
                        height: '24px',
                        borderRadius: '4px',
                        cursor: item.quantity >= item.product.stock_quantity ? 'not-allowed' : 'pointer',
                        opacity: item.quantity >= item.product.stock_quantity ? 0.5 : 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 'bold'
                      }}
                    >
                      +
                    </button>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', opacity: 0.8, paddingTop: '0.25rem', borderTop: '1px dashed rgba(255, 255, 255, 0.05)' }}>
                  <span>Subtotal:</span>
                  <strong>${itemTotal.toFixed(2)}</strong>
                </div>
              </div>
            );
          })
        )}
      </div>

      {items.length > 0 && (
        <div style={{
          borderTop: '1px solid rgba(255, 255, 255, 0.1)',
          paddingTop: '0.75rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span style={{ fontSize: '1rem', fontWeight: '500' }}>Total Venta:</span>
          <span style={{ fontSize: '1.4rem', fontWeight: '700', color: 'var(--secondary-color)' }}>
            ${total.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}
