let cart = [];
let allProducts = []; // Expose globally
let allClients = [];

document.addEventListener('DOMContentLoaded', async () => {
    // Load Products
    const res = await fetch('/api/products');
    allProducts = await res.json();

    // Load Clients
    try {
        const resClients = await fetch('/api/clients');
        if (resClients.ok) {
            allClients = await resClients.json();
            const clientSelect = document.getElementById('client-select');
            if (clientSelect) {
                // Keep default option
                clientSelect.innerHTML = '<option value="">Cliente Casual</option>';
                allClients.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c.id;
                    opt.textContent = c.name;
                    clientSelect.appendChild(opt);
                });
            }
        }
    } catch (err) {
        console.error("Error loading clients:", err);
    }

    // ... logic continues ...
    // renderProducts(allProducts); // Don't show all initially
    document.getElementById('product-results').innerHTML = '<div style="text-align:center; padding: 20px; color: #666;">Utiliza el buscador o el escáner para agregar productos.</div>';

    // Filter products
    document.getElementById('product-search').addEventListener('input', (e) => {
        const term = e.target.value.toLowerCase();
        const filtered = allProducts.filter(p =>
            p.name.toLowerCase().includes(term) ||
            (p.barcode && p.barcode.includes(term)) ||
            (p.item_number && p.item_number.toLowerCase().includes(term))
        );
        renderProducts(filtered);

        // Auto-add if exact barcode or item_number match
        const exactMatch = allProducts.find(p => p.barcode === term || (p.item_number && p.item_number.toLowerCase() === term));
        if (exactMatch) {
            addToCart(exactMatch);
            e.target.value = ''; // Clear for next scan
            renderProducts(allProducts);
            document.getElementById('product-search').focus();
        }
    });

    // Handle Enter on Quantity Input -> Focus Search
    const qtyInput = document.getElementById('pos-qty');
    if (qtyInput) {
        qtyInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                document.getElementById('product-search').focus();
            }
        });
    }

    // Handle Enter on Product Search -> Add First Result if any
    document.getElementById('product-search').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const term = e.target.value.toLowerCase();
            // If empty, do nothing
            if (!term) return;

            // Check if exact match exists (already handled by input, but safe to double check)
            const exact = allProducts.find(p => p.barcode === term || (p.item_number && p.item_number.toLowerCase() === term));
            if (exact) {
                // Input handler might have caught it, but if not:
                addToCart(exact);
                e.target.value = '';
                renderProducts(allProducts);
                return;
            }

            // Otherwise pick first visible result
            const filtered = allProducts.filter(p =>
                p.name.toLowerCase().includes(term) ||
                (p.barcode && p.barcode.includes(term)) ||
                (p.item_number && p.item_number.toLowerCase().includes(term))
            );

            if (filtered.length > 0) {
                addToCart(filtered[0]);
                e.target.value = '';
                renderProducts(allProducts);
            }
        }
    });
});

function renderProducts(products) {
    const container = document.getElementById('product-results');
    container.innerHTML = products.map(p => `
        <div onclick="addToCart({id: ${p.id}, name: '${p.name}', price: ${p.price}})"
             style="cursor: pointer; padding: 12px; border: 1px solid rgba(0,0,0,0.1); border-radius: 8px; text-align: center; background: rgba(255,255,255,0.4);">
            <div style="font-weight: 600;">${p.name}</div>
            ${p.item_number ? `<div style="font-size: 0.8rem; color: #555; background: #eee; display: inline-block; padding: 2px 6px; border-radius: 4px; margin: 4px 0;">#${p.item_number}</div>` : ''}
            <div style="color: var(--primary-color); font-weight: 700;">$${p.price}</div>
            <div style="font-size: 0.8rem; color: #666;">Stock: ${p.stock_quantity}</div>
        </div>
    `).join('');
}

function addToCart(product) {
    const qtyInput = document.getElementById('pos-qty');
    const qty = parseInt(qtyInput.value) || 1;

    const existing = cart.find(item => item.product_id === product.id);
    if (existing) {
        existing.quantity += qty;
    } else {
        cart.push({
            product_id: product.id,
            product_name: product.name,
            item_number: product.item_number, // Pass item number
            unit_price: product.price,
            quantity: qty
        });
    }

    // Reset Qty to 1 after add? Optional. Let's keep it for bulk scanning.
    qtyInput.value = 1;

    updateCart();
}

function updateCart() {
    const tbody = document.getElementById('cart-body');
    let total = 0;

    tbody.innerHTML = cart.map(item => {
        const lineTotal = item.unit_price * item.quantity;
        total += lineTotal;
        return `
        <tr>
            <td>
                ${item.product_name}
                ${item.item_number ? `<div style="font-size: 0.75rem; color: #666;">#${item.item_number}</div>` : ''}
            </td>
            <td>
                <div style="display: flex; align-items: center; gap: 4px;">
                    <button onclick="updateItemQty(${item.product_id}, -1)" style="width: 24px; height: 24px; border-radius: 4px; border: 1px solid #ccc; background: #eee; cursor: pointer;">-</button>
                    <span style="min-width: 20px; text-align: center;">${item.quantity}</span>
                    <button onclick="updateItemQty(${item.product_id}, 1)" style="width: 24px; height: 24px; border-radius: 4px; border: 1px solid #ccc; background: #eee; cursor: pointer;">+</button>
                </div>
            </td>
            <td>$${lineTotal.toFixed(2)}</td>
            <td><button onclick="removeFromCart(${item.product_id})" style="background:none; border:none; color: red; cursor:pointer;">&times;</button></td>
        </tr>
        `;
    }).join('');

    document.getElementById('cart-total').innerText = '$' + total.toFixed(2);
}

function updateItemQty(id, delta) {
    const item = cart.find(i => i.product_id === id);
    if (item) {
        const newQty = item.quantity + delta;
        if (newQty > 0) {
            item.quantity = newQty;
            updateCart();
        } else {
            // If qty goes to 0, ask to remove? Or just stop at 1?
            // Usually stop at 1. If they want to remove, use the X button.
            // Or allow removal if -1. Let's stop at 1 for safety.
        }
    }
}

function removeFromCart(id) {
    cart = cart.filter(i => i.product_id !== id);
    updateCart();
}

function checkout() {
    if (cart.length === 0) return alert("El carrito está vacío");

    const clientSelect = document.getElementById('client-select');
    const clientId = clientSelect ? clientSelect.value : "";
    const clientName = clientSelect ? clientSelect.options[clientSelect.selectedIndex].text : "Casual";

    // Calculate Total
    let total = cart.reduce((acc, item) => acc + (item.unit_price * item.quantity), 0);

    // Update Modal UI
    document.getElementById('modal-total-display').textContent = '$' + total.toFixed(2);
    document.getElementById('modal-client-display').textContent = clientName;
    document.getElementById('payment-amount').value = total.toFixed(2); // Default to full payment

    // Show Modal
    document.getElementById('payment-modal').style.display = 'flex';
    document.getElementById('payment-amount').focus();
    document.getElementById('payment-amount').select();
}

function closePaymentModal() {
    document.getElementById('payment-modal').style.display = 'none';
}

async function confirmCheckout() {
    const clientSelect = document.getElementById('client-select');
    const clientId = clientSelect ? clientSelect.value : null;

    let amountPaidInput = document.getElementById('payment-amount').value;
    let amountPaid = parseFloat(amountPaidInput);
    const paymentMethod = document.getElementById('payment-method').value;

    if (isNaN(amountPaid) || amountPaid < 0) {
        return alert("Por favor ingrese un monto válido");
    }

    const salesData = {
        items: cart.map(i => ({ product_id: i.product_id, quantity: i.quantity })),
        client_id: clientId ? parseInt(clientId) : null,
        amount_paid: amountPaid,
        payment_method: paymentMethod
    };

    // Disable button to prevent double submit
    const btn = document.querySelector('#payment-modal .btn');
    const originalText = btn.innerText;
    btn.disabled = true;
    btn.innerText = "Procesando...";

    try {
        const res = await fetch('/api/sales', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(salesData)
        });

        if (res.ok) {
            const sale = await res.json();

            closePaymentModal();

            // Ask to print Remito
            // If printed automatically, we can use window.open
            // User requested "Todo imprimible cada paso", so offering a print is key.
            if (confirm('Venta realizada con éxito. ¿Desea generar el Remito?')) {
                window.open(`/sales/${sale.id}/remito`, '_blank');
            }

            cart = [];
            updateCart();

            // Reload products to update stock
            const pRes = await fetch('/api/products');
            allProducts = await pRes.json();
            renderProducts(allProducts);
        } else {
            const err = await res.json();
            alert('Error: ' + err.detail);
        }
    } catch (e) {
        console.error(e);
        alert('Error de conexión o proceso: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = originalText;
        }
    }
}

function handlePaymentMethodChange() {
    const method = document.getElementById('payment-method').value;
    const totalText = document.getElementById('modal-total-display').innerText.replace('$', '');
    const total = parseFloat(totalText);
    const amountInput = document.getElementById('payment-amount');

    if (method === 'account') {
        amountInput.value = 0; // Default to 0 for debt
    } else {
        amountInput.value = total.toFixed(2); // Default to full payment
    }
}
