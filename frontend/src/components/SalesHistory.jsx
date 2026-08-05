'use client';
import React, { useState } from 'react';

export default function SalesHistory({ sales: initialSales = [], totalCount, userRole = 'guest', onCancelSale }) {
  const [salesList, setSalesList] = useState(initialSales);
  const [cancellingId, setCancellingId] = useState(null);

  React.useEffect(() => {
    setSalesList(initialSales);
  }, [initialSales]);

  const formatDate = (isoStr) => {
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoStr;
    }
  };

  const handleCancelClick = async (saleId) => {
    const reason = window.prompt(`Ingresá el motivo de anulación para la Venta #${saleId}:`, 'Anulación manual desde UI');
    if (!reason) return;

    setCancellingId(saleId);
    try {
      if (onCancelSale) {
        await onCancelSale(saleId, reason);
      } else {
        const formData = new FormData();
        formData.append('reason', reason);
        const res = await fetch(`/api/sales/${saleId}/cancel`, {
          method: 'POST',
          body: formData,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          alert('Error: ' + (err.detail || 'No se pudo anular la venta'));
          return;
        }
      }

      setSalesList(prev => prev.map(s => s.id === saleId ? { ...s, payment_status: 'cancelled' } : s));
    } catch (e) {
      alert('Error de red al anular venta: ' + e.message);
    } finally {
      setCancellingId(null);
    }
  };

  return (
    <div className="sdui-saleshistory" style={{
      background: 'var(--card-bg, rgba(255, 255, 255, 0.02))',
      border: '1px solid rgba(255, 255, 255, 0.05)',
      borderRadius: 'var(--border-radius)',
      padding: '1.2rem',
      color: 'var(--text-color, #fff)',
      fontFamily: 'var(--font-family)',
      overflowX: 'auto'
    }}>
      <h2 style={{ margin: '0 0 1rem 0', fontSize: '1.2rem', fontWeight: '600', borderBottom: '1px solid rgba(255, 255, 255, 0.1)', paddingBottom: '0.5rem' }}>
        Ventas Recientes
      </h2>

      {salesList.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '2rem 1rem', color: 'var(--text-color)', opacity: 0.3, fontSize: '0.9rem' }}>
          No se registraron ventas en esta sesión.
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', minWidth: '450px' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)', textAlign: 'left', opacity: 0.7 }}>
              <th style={{ padding: '0.5rem' }}>ID</th>
              <th style={{ padding: '0.5rem' }}>Fecha/Hora</th>
              <th style={{ padding: '0.5rem' }}>Método</th>
              <th style={{ padding: '0.5rem' }}>Estado</th>
              <th style={{ padding: '0.5rem', textAlign: 'right' }}>Total</th>
              <th style={{ padding: '0.5rem', textAlign: 'center' }}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {salesList.map((sale) => {
              const isCancelled = sale.payment_status === 'cancelled';
              const isPaid = sale.payment_status === 'paid';
              return (
                <tr key={sale.id} style={{
                  borderBottom: '1px solid rgba(255, 255, 255, 0.03)',
                  opacity: isCancelled ? 0.55 : 1,
                  background: isCancelled ? 'rgba(239, 68, 68, 0.05)' : 'transparent',
                }}>
                  <td style={{ padding: '0.5rem', fontWeight: '600' }}>#{sale.id}</td>
                  <td style={{ padding: '0.5rem', opacity: 0.8 }}>{formatDate(sale.timestamp)}</td>
                  <td style={{ padding: '0.5rem', textTransform: 'capitalize', opacity: 0.8 }}>{sale.payment_method}</td>
                  <td style={{ padding: '0.5rem' }}>
                    <span style={{
                      background: isCancelled ? 'rgba(239, 68, 68, 0.2)' : isPaid ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                      color: isCancelled ? '#ef4444' : isPaid ? '#10b981' : '#f59e0b',
                      padding: '0.15rem 0.4rem',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: '600'
                    }}>
                      {isCancelled ? '🚫 Anulada' : isPaid ? 'Pagado' : 'Impago'}
                    </span>
                  </td>
                  <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: '700', color: isCancelled ? 'inherit' : 'var(--secondary-color)', textDecoration: isCancelled ? 'line-through' : 'none' }}>
                    ${(sale.total_amount || 0).toFixed(2)}
                  </td>
                  <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                    {userRole === 'admin' && !isCancelled && (
                      <button
                        disabled={cancellingId === sale.id}
                        onClick={() => handleCancelClick(sale.id)}
                        style={{
                          background: 'rgba(239, 68, 68, 0.2)',
                          color: '#ef4444',
                          border: '1px solid rgba(239, 68, 68, 0.3)',
                          padding: '0.2rem 0.5rem',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          cursor: cancellingId === sale.id ? 'not-allowed' : 'pointer',
                          fontWeight: '600'
                        }}
                      >
                        {cancellingId === sale.id ? 'Anulando...' : 'Anular'}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

