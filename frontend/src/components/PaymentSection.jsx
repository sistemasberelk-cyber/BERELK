'use client';
import React, { useState } from 'react';

export default function PaymentSection({ cartItems, onProcessSale, processing, currentUserClient, isCreditEnabled }) {
  const canUseCredit = isCreditEnabled ?? currentUserClient?.credit_enabled ?? false;

  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [amountPaid, setAmountPaid] = useState('');
  const [splitCash, setSplitCash] = useState('');
  const [splitTransfer, setSplitTransfer] = useState('');
  const [clientId, setClientId] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const calculateItemPrice = (item) => {
    const raw = item.price_type === 'bulk'
      ? (item.product.price_bulk ?? item.product.price)
      : (item.product.price_retail ?? item.product.price);
    return parseFloat(raw || 0);
  };

  const total = cartItems.reduce((sum, item) => {
    return sum + (calculateItemPrice(item) * item.quantity);
  }, 0);

  const handlePaymentMethodChange = (newMethod) => {
    setPaymentMethod(newMethod);
    if (newMethod === 'credit') {
      setAmountPaid('0');
      setSplitCash('');
      setSplitTransfer('');
    } else if (newMethod === 'mixed') {
      const half = (total / 2).toFixed(2);
      setSplitCash(half);
      setSplitTransfer(half);
      setAmountPaid(total.toFixed(2));
    } else {
      setSplitCash('');
      setSplitTransfer('');
      setAmountPaid(total.toFixed(2));
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (cartItems.length === 0) {
      setErrorMsg('El carrito está vacío.');
      return;
    }

    const isCredit = paymentMethod === 'credit';
    const normalizedMethod = isCredit ? 'cuenta_corriente' : paymentMethod;
    const finalAmountPaid = isCredit ? 0 : (amountPaid ? parseFloat(amountPaid) : total);

    const payload = {
      payment_method: normalizedMethod,
      client_id: clientId ? parseInt(clientId, 10) : null,
      amount_paid: finalAmountPaid,
      split_cash: paymentMethod === 'mixed' && splitCash ? parseFloat(splitCash) : null,
      split_transfer: paymentMethod === 'mixed' && splitTransfer ? parseFloat(splitTransfer) : null
    };

    if (isCredit && !payload.client_id) {
      setErrorMsg('Debe seleccionar un ID de cliente para venta a Cuenta Corriente.');
      return;
    }

    // Validation for mixed payment
    if (paymentMethod === 'mixed') {
      const sum = (payload.split_cash || 0) + (payload.split_transfer || 0);
      if (Math.abs(sum - total) > 0.05) {
        setErrorMsg(`Los montos mixtos ($${sum.toFixed(2)}) deben coincidir con el total ($${total.toFixed(2)}).`);
        return;
      }
    }

    onProcessSale(payload);
  };

  return (
    <div className="sdui-payment" style={{
      background: 'var(--card-bg, rgba(255, 255, 255, 0.02))',
      border: '1px solid rgba(255, 255, 255, 0.05)',
      borderRadius: 'var(--border-radius)',
      padding: '1.2rem',
      color: 'var(--text-color, #fff)',
      fontFamily: 'var(--font-family)'
    }}>
      <h2 style={{ margin: '0 0 1rem 0', fontSize: '1.2rem', fontWeight: '600', borderBottom: '1px solid rgba(255, 255, 255, 0.1)', paddingBottom: '0.5rem' }}>
        Finalizar Transacción
      </h2>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
        {/* Client ID */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={{ fontSize: '0.8rem', opacity: 0.8 }}>ID Cliente {paymentMethod === 'credit' ? '(Requerido for Deuda):' : '(Opcional):'}</label>
          <input
            type="number"
            placeholder="Ej: 1"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            style={{
              background: 'var(--card-bg, rgba(0, 0, 0, 0.2))',
              border: paymentMethod === 'credit' && !clientId ? '1px solid #ef4444' : '1px solid rgba(255, 255, 255, 0.1)',
              padding: '0.5rem',
              borderRadius: 'calc(var(--border-radius) / 2)',
              color: 'var(--text-color, #fff)',
              outline: 'none'
            }}
          />
        </div>

        {/* Payment Method */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={{ fontSize: '0.8rem', opacity: 0.8 }}>Método de Pago:</label>
          <select
            value={paymentMethod}
            onChange={(e) => handlePaymentMethodChange(e.target.value)}
            style={{
              background: 'var(--card-bg, rgba(0, 0, 0, 0.3))',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              padding: '0.5rem',
              borderRadius: 'calc(var(--border-radius) / 2)',
              color: 'var(--text-color, #fff)',
              outline: 'none',
              cursor: 'pointer'
            }}
          >
            <option value="cash">Efectivo</option>
            <option value="transfer">Transferencia</option>
            <option value="mixed">Pago Mixto (Efectivo + Transf.)</option>
            {canUseCredit && <option value="credit">Cuenta Corriente (Deuda)</option>}
          </select>
        </div>

        {/* Mixed details */}
        {paymentMethod === 'mixed' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', background: 'var(--card-bg, rgba(0, 0, 0, 0.1))', padding: '0.75rem', borderRadius: '4px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <label style={{ fontSize: '0.75rem', opacity: 0.8 }}>Efectivo:</label>
              <input
                type="number"
                step="0.01"
                value={splitCash}
                onChange={(e) => setSplitCash(e.target.value)}
                style={{
                  background: 'var(--card-bg, rgba(0, 0, 0, 0.2))',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  padding: '0.4rem',
                  borderRadius: '4px',
                  color: 'var(--text-color, #fff)',
                  fontSize: '0.85rem'
                }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <label style={{ fontSize: '0.75rem', opacity: 0.8 }}>Transferencia:</label>
              <input
                type="number"
                step="0.01"
                value={splitTransfer}
                onChange={(e) => setSplitTransfer(e.target.value)}
                style={{
                  background: 'var(--card-bg, rgba(0, 0, 0, 0.2))',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  padding: '0.4rem',
                  borderRadius: '4px',
                  color: 'var(--text-color, #fff)',
                  fontSize: '0.85rem'
                }}
              />
            </div>
          </div>
        )}

        {/* Amount Paid */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={{ fontSize: '0.8rem', opacity: 0.8 }}>Monto Cobrado:</label>
          <input
            type="number"
            step="0.01"
            value={amountPaid}
            onChange={(e) => setAmountPaid(e.target.value)}
            disabled={paymentMethod === 'credit'}
            style={{
              background: 'var(--card-bg, rgba(0, 0, 0, 0.2))',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              padding: '0.5rem',
              borderRadius: 'calc(var(--border-radius) / 2)',
              color: 'var(--text-color, #fff)',
              outline: 'none',
              opacity: paymentMethod === 'credit' ? 0.5 : 1
            }}
          />
          {paymentMethod === 'credit' && (
            <div style={{ color: '#38bdf8', fontSize: '0.8rem', marginTop: '0.25rem', fontWeight: '500' }}>
              ℹ️ Se registrará como deuda del cliente por ${total.toFixed(2)} (monto cobrado $0.00).
            </div>
          )}
        </div>

        {errorMsg && (
          <div style={{ color: '#ef4444', fontSize: '0.8rem', marginTop: '0.25rem', fontWeight: '500' }}>
            ⚠️ {errorMsg}
          </div>
        )}

        <button
          type="submit"
          disabled={processing || cartItems.length === 0}
          style={{
            background: 'var(--secondary-color)',
            color: 'var(--text-color, #fff)',
            border: 'none',
            padding: '0.85rem',
            borderRadius: 'calc(var(--border-radius) / 2)',
            cursor: (processing || cartItems.length === 0) ? 'not-allowed' : 'pointer',
            fontWeight: '700',
            fontSize: '1rem',
            fontFamily: 'var(--font-family)',
            marginTop: '0.5rem',
            transition: 'opacity 0.2s',
            opacity: (processing || cartItems.length === 0) ? 0.6 : 1
          }}
          onMouseEnter={(e) => {
            if (!processing && cartItems.length > 0) e.target.style.opacity = 0.9;
          }}
          onMouseLeave={(e) => {
            if (!processing && cartItems.length > 0) e.target.style.opacity = 1;
          }}
        >
          {processing ? 'Procesando Venta...' : 'Cerrar Venta'}
        </button>
      </form>
    </div>
  );
}

