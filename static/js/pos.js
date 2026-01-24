let cart = [];
let allProducts = [];

// Load products on start
document.addEventListener('DOMContentLoaded', async () => {
    const res = await fetch('/api/products');
    allProducts = await res.json();
    renderProducts(allProducts);
});

// Filter products
document.getElementById('product-search').addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase();
    const filtered = allProducts.filter(p =>
        p.name.toLowerCase().includes(term) ||
        (p.barcode && p.barcode.includes(term))
    );
    renderProducts(filtered);

    // Auto-add if exact barcode match
    const exactMatch = allProducts.find(p => p.barcode === term);
    if (exactMatch) {
        addToCart(exactMatch);
        e.target.value = ''; // Clear for next scan
        renderProducts(allProducts);
    }
});

function renderProducts(products) {
    const container = document.getElementById('product-results');
    container.innerHTML = products.map(p => `
        <div onclick="addToCart({id: ${p.id}, name: '${p.name}', price: ${p.price}})" 
             style="cursor: pointer; padding: 12px; border: 1px solid rgba(0,0,0,0.1); border-radius: 8px; text-align: center; background: rgba(255,255,255,0.4);">
            <div style="font-weight: 600;">${p.name}</div>
            <div style="color: var(--primary-color); font-weight: 700;">$${p.price}</div>
            <div style="font-size: 0.8rem; color: #666;">Stock: ${p.stock_quantity}</div>
        </div>
    `).join('');
}

function addToCart(product) {
    const existing = cart.find(i => i.id === product.id);
    if (existing) {
        existing.qty++;
    } else {
        cart.push({ ...product, qty: 1 });
    }
    updateCart();
}

function updateCart() {
    const tbody = document.getElementById('cart-body');
    let total = 0;

    tbody.innerHTML = cart.map(item => {
        const lineTotal = item.price * item.qty;
        total += lineTotal;
        return `
        <tr>
            <td>${item.name}</td>
            <td>${item.qty}</td>
            <td>$${lineTotal.toFixed(2)}</td>
            <td><button onclick="removeFromCart(${item.id})" style="background:none; border:none; color: red; cursor:pointer;">&times;</button></td>
        </tr>
        `;
    }).join('');

    document.getElementById('cart-total').innerText = '$' + total.toFixed(2);
}

function removeFromCart(id) {
    cart = cart.filter(i => i.id !== id);
    updateCart();
}

async function checkout() {
    if (cart.length === 0) return alert("El carrito está vacío");

    const salesData = {
        items: cart.map(i => ({ product_id: i.id, quantity: i.qty }))
    };

    try {
        const res = await fetch('/api/sales', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(salesData)
        });

        if (res.ok) {
            alert('Venta realizada con éxito');
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
        alert('Error de conexión');
    }
}
