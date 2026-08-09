"""services/label_service.py — Unificación de generación de etiquetas y barcodes"""
from __future__ import annotations
import os
import re
import logging
from typing import List, Optional, Dict, Any
from barcode import Code128
from barcode.writer import ImageWriter
from sqlmodel import Session, select, col
from database.models import Product

logger = logging.getLogger(__name__)

class LabelService:
    STATIC_DIR = "static/barcodes"

    @staticmethod
    def ensure_barcode_image(barcode_value: str) -> Optional[str]:
        """Genera la imagen PNG del barcode si no existe. Retorna el nombre del archivo."""
        if not barcode_value:
            return None
        
        # Sanitizar nombre de archivo
        bc_filename = re.sub(r"[^A-Za-z0-9._-]", "_", barcode_value).strip("._-")
        if not bc_filename:
            return None
            
        os.makedirs(LabelService.STATIC_DIR, exist_ok=True)
        full_path = os.path.join(LabelService.STATIC_DIR, bc_filename)
        
        if not os.path.exists(full_path + ".png"):
            try:
                Code128(barcode_value, writer=ImageWriter()).save(full_path)
            except Exception:
                logger.exception("Error generando barcode para: %s", barcode_value)
                return None
                
        return f"{bc_filename}.png"

    @staticmethod
    def prepare_labels_data(session: Session, tenant_id: int, product_ids: List[int]) -> List[Dict[str, Any]]:
        """Prepara los datos de productos para el template de etiquetas."""
        products = session.exec(
            select(Product).where(
                col(Product.id).in_(product_ids),
                Product.tenant_id == tenant_id
            )
        ).all()
        
        p_map = {p.id: p for p in products}
        labels_data = []
        for pid in product_ids:
            p = p_map.get(pid)
            if not p:
                continue
            bc_file = LabelService.ensure_barcode_image(str(p.barcode or "").strip())
            if not bc_file:
                continue
                
            labels_data.append({
                "name": p.name,
                "price": p.price_retail or p.price,
                "barcode": p.barcode,
                "barcode_file": bc_file,
                "category": p.category,
                "description": p.description,
                "item_number": p.item_number
            })
        return labels_data

