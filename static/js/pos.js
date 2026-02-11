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
    container.innerHTML = products.map(p => {
        const hasBulk = p.price_bulk && p.price_bulk > 0;
        const displayPrice = hasBulk ? p.price_bulk : p.price;

        return `
        <div style="cursor: pointer; padding: 12px; border: 1px solid rgba(0,0,0,0.1); border-radius: 8px; text-align: center; background: rgba(255,255,255,0.4); position: relative;">
            <!-- Edit Button (Top Right) -->
            <button onclick="event.stopPropagation(); quickEditProduct(${p.id})" 
                style="position: absolute; top: 4px; right: 4px; background: #2563eb; color: white; border: none; border-radius: 4px; padding: 4px 8px; cursor: pointer; font-size: 0.75rem; z-index: 10;">
                ✏️
            </button>
            
            <!-- Product Card (Clickable to Add) -->
            <div onclick='addToCart(${JSON.stringify(p)})'>
                <div style="font-weight: 600;">${p.name}</div>
                ${p.item_number ? `<div style="font-size: 0.8rem; color: #555; background: #eee; display: inline-block; padding: 2px 6px; border-radius: 4px; margin: 4px 0;">#${p.item_number}</div>` : ''}
                <div style="color: var(--primary-color); font-weight: 700;">
                    $${displayPrice}
                    ${hasBulk ? '<span style="font-size: 0.7rem; color: #b45309; display: block;">(Precio Bulto)</span>' : ''}
                </div>
                <div style="font-size: 0.8rem; color: #666;">Stock: ${p.stock_quantity}</div>
            </div>
        </div>
        `;
    }).join('');
}

async function addToCart(product) {
    // 1. Prepare Price Options
    const prices = [
        { key: 'unit', label: 'Por Unidad', val: product.price },
        { key: 'retail', label: 'Por Mostrador', val: product.price_retail },
        { key: 'bulk', label: 'Por Bulto', val: product.price_bulk }
    ];

    // Build options for radio selector, filter out null/0 prices
    const inputOptions = {};
    let defaultKey = 'bulk'; // Default based on previous request

    prices.forEach(p => {
        if (p.val && p.val > 0) {
            inputOptions[p.key] = `${p.label} ($${p.val})`;
        } else if (p.key === 'unit') {
            // Always allow unit even if 0 (though unlikely)
            inputOptions[p.key] = `${p.label} ($${p.val || 0})`;
        }
    });

    // If only one option, skip? No, user wants to be asked.
    const { value: selectedKey } = await Swal.fire({
        title: 'Seleccionar Tarifa',
        text: product.name,
        input: 'radio',
        inputOptions: inputOptions,
        inputValue: inputOptions[defaultKey] ? defaultKey : 'unit',
        showCancelButton: true,
        confirmButtonText: 'Seleccionar Qty',
        confirmButtonColor: '#2563eb',
        cancelButtonText: 'Cancelar'
    });

    if (!selectedKey) return;

    const finalPrice = prices.find(p => p.key === selectedKey).val;
    const finalLabel = prices.find(p => p.key === selectedKey).label;

    // 2. Ask for Quantity
    const { value: qty } = await Swal.fire({
        title: 'Cantidad',
        html: `Producto: <b>${product.name}</b><br>Precio: <span style="color:green; font-weight:bold;">${finalLabel} ($${finalPrice})</span>`,
        input: 'number',
        inputValue: document.getElementById('pos-qty').value || 1,
        inputAttributes: { min: 1, step: 1 },
        showCancelButton: true,
        confirmButtonText: 'Agregar al Carrito'
    });

    if (!qty || qty <= 0) return;

    const quantity = parseInt(qty);

    // 3. Add to Data Structure
    const existing = cart.find(item => item.product_id === product.id && item.unit_price === finalPrice);
    if (existing) {
        existing.quantity += quantity;
    } else {
        cart.push({
            product_id: product.id,
            product_name: product.name,
            item_number: product.item_number,
            unit_price: finalPrice,
            quantity: quantity,
            price_type: finalLabel
        });
    }

    // Reset Qty to 1 and focus search
    document.getElementById('pos-qty').value = 1;
    document.getElementById('product-search').value = '';
    document.getElementById('product-search').focus();

    updateCart();

    // Small Toast Feedback
    Swal.fire({
        toast: true,
        position: 'top-end',
        icon: 'success',
        title: 'Agregado',
        showConfirmButton: false,
        timer: 1000
    });
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
                <div style="font-size: 0.75rem; color: #666;">
                    ${item.item_number ? `#${item.item_number} | ` : ''}
                    <span style="color: #2563eb; font-weight: bold;">${item.price_type}</span>
                </div>
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

async function quickEditProduct(productId) {
    // Find product in allProducts
    const product = allProducts.find(p => p.id === productId);
    if (!product) {
        Swal.fire('Error', 'Producto no encontrado', 'error');
        return;
    }

    const { value: formValues } = await Swal.fire({
        title: `Editar: ${product.name}`,
        html: `
            <div style="text-align: left;">
                <label style="font-weight: bold;">Precio Unitario:</label>
                <input id="edit-price" type="number" step="0.01" value="${product.price || 0}" class="swal2-input" style="width: 90%;">
                
                <label style="font-weight: bold; margin-top: 10px; display: block;">Precio Mostrador:</label>
                <input id="edit-price-retail" type="number" step="0.01" value="${product.price_retail || ''}" class="swal2-input" style="width: 90%;">
                
                <label style="font-weight: bold; margin-top: 10px; display: block;">Precio Bulto:</label>
                <input id="edit-price-bulk" type="number" step="0.01" value="${product.price_bulk || ''}" class="swal2-input" style="width: 90%;">
                
                <label style="font-weight: bold; margin-top: 10px; display: block;">Stock:</label>
                <input id="edit-stock" type="number" value="${product.stock_quantity || 0}" class="swal2-input" style="width: 90%;">
            </div>
        `,
        focusConfirm: false,
        showCancelButton: true,
        confirmButtonText: 'Guardar',
        cancelButtonText: 'Cancelar',
        preConfirm: () => {
            return {
                price: parseFloat(document.getElementById('edit-price').value),
                price_retail: parseFloat(document.getElementById('edit-price-retail').value) || null,
                price_bulk: parseFloat(document.getElementById('edit-price-bulk').value) || null,
                stock: parseInt(document.getElementById('edit-stock').value)
            }
        }
    });

    if (formValues) {
        try {
            const formData = new FormData();
            formData.append('name', product.name);
            formData.append('price', formValues.price);
            formData.append('stock', formValues.stock);
            formData.append('description', product.description || '');
            formData.append('barcode', product.barcode || '');
            formData.append('category', product.category || '');
            formData.append('item_number', product.item_number || '');
            formData.append('cant_bulto', product.cant_bulto || '');
            formData.append('numeracion', product.numeracion || '');
            if (formValues.price_retail) formData.append('price_retail', formValues.price_retail);
            if (formValues.price_bulk) formData.append('price_bulk', formValues.price_bulk);

            const res = await fetch(`/api/products/${productId}`, {
                method: 'PUT',
                body: formData
            });

            if (res.ok) {
                Swal.fire('Éxito', 'Producto actualizado', 'success');
                // Reload products
                const pRes = await fetch('/api/products');
                allProducts = await pRes.json();
                // Re-render current search
                const term = document.getElementById('product-search').value.toLowerCase();
                const filtered = allProducts.filter(p =>
                    p.name.toLowerCase().includes(term) ||
                    (p.barcode && p.barcode.includes(term)) ||
                    (p.item_number && p.item_number.toLowerCase().includes(term))
                );
                renderProducts(filtered);
            } else {
                Swal.fire('Error', 'No se pudo actualizar', 'error');
            }
        } catch (e) {
            Swal.fire('Error', 'Fallo de conexión', 'error');
        }
    }
}

