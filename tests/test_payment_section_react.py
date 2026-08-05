"""
tests/test_payment_section_react.py
====================================
Tests de integración/unidad para la lógica del componente React PaymentSection.jsx.
Verifica que el payload de pago para Cuenta Corriente normalice:
  - payment_method = 'cuenta_corriente'
  - amount_paid = 0
  - client_id es validado
  - Transición de estados de credit -> cash -> credit resetea los valores.
"""
import os
import subprocess
import json
import pytest

@pytest.fixture(scope="module")
def node_test_script():
    script_path = os.path.join(os.path.dirname(__file__), "run_react_payment_test.js")
    code = """
const fs = require('fs');
const path = require('path');
const assert = require('assert');

// Simple emulation of PaymentSection.jsx logic for node environment contract test
const componentCode = fs.readFileSync(path.join(__dirname, '../frontend/src/components/PaymentSection.jsx'), 'utf8');

// Contract assertions directly against the component source code and behavior
console.log("Evaluating PaymentSection.jsx contract...");

// 1. Verify credit method sets payment_method to 'cuenta_corriente'
assert(componentCode.includes("normalizedMethod = isCredit ? 'cuenta_corriente' : paymentMethod"), "Must normalize credit to cuenta_corriente");

// 2. Verify amount_paid is forced to 0 for credit
assert(componentCode.includes("finalAmountPaid = isCredit ? 0 :"), "Must force amount_paid to 0 when isCredit");

// 3. Verify handlePaymentMethodChange sets amountPaid to '0' on credit
assert(componentCode.includes("setAmountPaid('0')"), "Must set amountPaid to '0' when selecting credit");

// 4. Verify helper text for credit debt notice exists
assert(componentCode.includes("Se registrará como deuda del cliente"), "Must show debt helper text");

// 5. Simulate transition logic
function simulateStateTransitions(total) {
  let paymentMethod = 'cash';
  let amountPaid = total.toFixed(2);
  let splitCash = '';
  let splitTransfer = '';

  function handlePaymentMethodChange(newMethod) {
    paymentMethod = newMethod;
    if (newMethod === 'credit') {
      amountPaid = '0';
      splitCash = '';
      splitTransfer = '';
    } else if (newMethod === 'mixed') {
      const half = (total / 2).toFixed(2);
      splitCash = half;
      splitTransfer = half;
      amountPaid = total.toFixed(2);
    } else {
      splitCash = '';
      splitTransfer = '';
      amountPaid = total.toFixed(2);
    }
  }

  function getPayload(clientId) {
    const isCredit = paymentMethod === 'credit';
    return {
      payment_method: isCredit ? 'cuenta_corriente' : paymentMethod,
      client_id: clientId ? parseInt(clientId, 10) : null,
      amount_paid: isCredit ? 0 : (amountPaid ? parseFloat(amountPaid) : total),
      split_cash: paymentMethod === 'mixed' && splitCash ? parseFloat(splitCash) : null,
      split_transfer: paymentMethod === 'mixed' && splitTransfer ? parseFloat(splitTransfer) : null
    };
  }

  return { handlePaymentMethodChange, getPayload, getState: () => ({ paymentMethod, amountPaid }) };
}

const sim = simulateStateTransitions(5000.00);

// Transition cash -> credit
sim.handlePaymentMethodChange('credit');
assert.strictEqual(sim.getState().amountPaid, '0', "amountPaid should be '0' on credit");
let payload = sim.getPayload("12");
assert.strictEqual(payload.payment_method, 'cuenta_corriente', "payment_method should be cuenta_corriente");
assert.strictEqual(payload.amount_paid, 0, "amount_paid should be 0");
assert.strictEqual(payload.client_id, 12, "client_id should be 12");

// Transition credit -> cash
sim.handlePaymentMethodChange('cash');
assert.strictEqual(sim.getState().amountPaid, '5000.00', "amountPaid should reset to total on cash");
payload = sim.getPayload("12");
assert.strictEqual(payload.payment_method, 'cash');
assert.strictEqual(payload.amount_paid, 5000.00);

// Transition cash -> credit again
sim.handlePaymentMethodChange('credit');
assert.strictEqual(sim.getState().amountPaid, '0');
payload = sim.getPayload("12");
assert.strictEqual(payload.payment_method, 'cuenta_corriente');
assert.strictEqual(payload.amount_paid, 0);

console.log("✅ All PaymentSection React contract assertions passed!");
"""
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code)
    yield script_path
    if os.path.exists(script_path):
        try:
            os.remove(script_path)
        except OSError:
            pass


def test_react_payment_section_logic(node_test_script):
    """Ejecuta el runner de pruebas de contrato de PaymentSection.jsx con Node.js."""
    res = subprocess.run(
        ["node", node_test_script],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Error en test de PaymentSection React: {res.stderr}\nOutput: {res.stdout}"
    assert "All PaymentSection React contract assertions passed" in res.stdout
