'use client';
import React from 'react';
import Header from './Header';
import ProductSearchBox from './ProductSearchBox';
import CatalogGrid from './CatalogGrid';
import CartDetail from './CartDetail';
import PaymentSection from './PaymentSection';
import SalesHistory from './SalesHistory';
import Footer from './Footer';

const componentMap = {
  header: Header,
  productsearchbox: ProductSearchBox,
  search: ProductSearchBox,
  cataloggrid: CatalogGrid,
  catalog: CatalogGrid,
  cartdetail: CartDetail,
  cart: CartDetail,
  paymentsection: PaymentSection,
  payment: PaymentSection,
  saleshistory: SalesHistory,
  sales: SalesHistory,
  footer: Footer
};

export default function DynamicViewRenderer({
  layout,
  user,
  onLogout,
  searchValue,
  onSearchValueChange,
  onSearch,
  products,
  page,
  pages,
  totalProducts,
  onPageChange,
  onAddToCart,
  cartItems,
  onUpdateQuantity,
  onUpdatePriceType,
  onRemoveItem,
  onClearCart,
  onProcessSale,
  processing,
  sales
}) {
  if (!layout || !layout.modules) {
    return <div style={{ color: 'var(--text-color, #fff)', padding: '2rem', textAlign: 'center' }}>Cargando diseño...</div>;
  }

  const gridCols = layout.grid_cols || 12;
  const layoutStructure = layout.layout_structure || {};

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: `repeat(${gridCols}, 1fr)`,
      gap: '1.5rem',
      width: '100%',
      maxWidth: '1400px',
      margin: '0 auto',
      padding: '1.5rem',
      boxSizing: 'border-box'
    }}>
      {layout.modules.map((moduleName, index) => {
        const key = moduleName.toLowerCase();
        const Component = componentMap[key];

        if (!Component) {
          console.warn(`Módulo desconocido en Server-Driven UI: ${moduleName}`);
          return null;
        }

        // Try to match in layoutStructure (case-sensitive or capitalized)
        const struct = layoutStructure[moduleName] || 
                       layoutStructure[moduleName.charAt(0).toUpperCase() + moduleName.slice(1).toLowerCase()] || 
                       layoutStructure[key];

        const itemStyle = {
          gridColumn: struct?.col_span ? `span ${struct.col_span}` : 'span 12',
          gridRow: struct?.row ? `${struct.row}` : 'auto'
        };

        // Determine props based on component map key
        let componentProps = {};
        if (key === 'header') {
          componentProps = { user, onLogout };
        } else if (key === 'productsearchbox' || key === 'search') {
          componentProps = { value: searchValue, onChange: onSearchValueChange, onSearch };
        } else if (key === 'cataloggrid' || key === 'catalog') {
          componentProps = { products, page, pages, total: totalProducts, onPageChange, onAddToCart };
        } else if (key === 'cartdetail' || key === 'cart') {
          componentProps = { items: cartItems, onUpdateQuantity, onUpdatePriceType, onRemoveItem, onClearCart };
        } else if (key === 'paymentsection' || key === 'payment') {
          componentProps = { cartItems, onProcessSale, processing };
        } else if (key === 'saleshistory' || key === 'sales') {
          componentProps = { sales, totalCount: sales.length, userRole: user?.role || 'guest' };
        }

        return (
          <div key={`${moduleName}-${index}`} style={itemStyle}>
            <Component {...componentProps} />
          </div>
        );
      })}
    </div>
  );
}
