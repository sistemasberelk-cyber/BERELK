from typing import Optional, List
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship

# --- User Model ---
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str  # We will store bcrypt hash, not plain text
    full_name: Optional[str] = None
    role: str = Field(default="admin")  # admin, cashier
    is_active: bool = Field(default=True)
    
    sales: List["Sale"] = Relationship(back_populates="user")

# --- Product Model ---
class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    barcode: str = Field(unique=True, index=True) 
    price: float = Field(default=0.0)
    cost_price: float = Field(default=0.0) # For profit calculation
    stock_quantity: int = Field(default=0)
    min_stock_level: int = Field(default=5) # Alert level
    category: Optional[str] = None
    image_url: Optional[str] = None

# --- Sale Models (Header & Detail) ---
class Sale(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_amount: float = Field(default=0.0)
    payment_method: str = Field(default="cash") # cash, card, transfer
    
    # Foreign Keys
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    user: Optional[User] = Relationship(back_populates="sales")
    
    items: List["SaleItem"] = Relationship(back_populates="sale")

class SaleItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sale_id: Optional[int] = Field(default=None, foreign_key="sale.id")
    product_id: Optional[int] = Field(default=None, foreign_key="product.id")
    
    product_name: str # Snapshot in case product name changes
    quantity: int
    unit_price: float
    total: float
    
    sale: Optional[Sale] = Relationship(back_populates="items")
