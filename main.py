"""VibeCloud Cloud SaaS — Main Application (Refactored)"""
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select, func
from contextlib import asynccontextmanager
from datetime import datetime, date
import os
import logging
import httpx
from pythonjsonlogger import jsonlogger
from core.config import settings
from database.session import create_db_and_tables, get_session, engine
from database.models import Product, Sale, Settings, User, Tenant
from database.seed_data import seed_products
from services.auth_service import AuthService
from web.dependencies import get_current_user, get_settings, get_tenant, require_auth
from web.compat_templates import CompatTemplates

# Routers
from routers.auth import router as auth_router
from routers.admin import router as admin_router
from routers.products import router as products_router
from routers.sales import router as sales_router
from routers.clients import router as clients_router
from routers.suppliers import router as suppliers_router
from routers.cash import router as cash_router
from routers.reports import router as reports_router
from routers.picking import router as picking_router
from routers.wms import router as wms_router

# API V1 Routers
from routers.api.v1.auth import router as auth_v1_router
from routers.api.v1.products import router as products_v1_router
from routers.api.v1.sales import router as sales_v1_router
from routers.api.v1.ui_config import router as ui_config_v1_router
from routers.api.v1.inventory import router as inventory_v1_router
from routers.api.v1.medusa_sync import router as medusa_sync_v1_router
from routers.ai import router as ai_router
from routers.superadmin import router as superadmin_router
from routers.store import router as store_router

def setup_logging():
    handlers = []
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    
    try:
        os.makedirs('logs', exist_ok=True)
        logHandler = logging.FileHandler(filename='logs/vibecloud.log')
        logHandler.setFormatter(formatter)
        handlers.append(logHandler)
    except Exception:
        pass  # File logging not available (e.g. read-only filesystem on Render)
    
    streamHandler = logging.StreamHandler()
    streamHandler.setFormatter(formatter)
    handlers.append(streamHandler)
    
    logging.basicConfig(level=logging.INFO, handlers=handlers)

setup_logging()
logger = logging.getLogger(__name__)

from sqlalchemy import text

def ensure_schema_compatibility(session: Session):
    """
    DEPRECATED: This block is deprecated and has been removed to speed up boot.
    """
    pass

templates = CompatTemplates(directory="templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run migrations on startup
    try:
        from alembic import command
        from alembic.config import Config
        alembic_cfg = Config("alembic.ini")
        # Ensure url is set from env
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations completed successfully.")
    except Exception as e:
        logger.error(f"Alembic migration failed: {e}")
        # Fallback to simple table creation if alembic fails
        try:
            create_db_and_tables()
        except Exception as e2:
            logger.error(f"Fallback create_db_and_tables also failed: {e2}")

    # Ensure storefront_template column exists in settings
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN storefront_template VARCHAR DEFAULT 'elegante'"))
            conn.commit()
    except Exception:
        pass  # Column likely already exists

    # Ensure ai_tier and ai_credits columns exist in tenant
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE tenant ADD COLUMN ai_tier VARCHAR DEFAULT 'free'"))
            conn.execute(text("ALTER TABLE tenant ADD COLUMN ai_credits INTEGER DEFAULT 100"))
            conn.commit()
    except Exception:
        pass  # Columns likely already exist

    # Ensure medusa_product_id column exists in product (added after initial deploy)
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE product ADD COLUMN IF NOT EXISTS medusa_product_id VARCHAR"))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_product_medusa_product_id "
                "ON product (medusa_product_id)"
            ))
            conn.commit()
        logger.info("medusa_product_id column ensured in product table.")
    except Exception as e:
        logger.warning(f"medusa_product_id migration skipped (non-fatal): {e}")

    # Ensure client_id column exists in user table (added for B2B client portal)
    try:
        with engine.connect() as conn:
            conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS client_id INTEGER'))
            conn.commit()
        logger.info("client_id column ensured in user table.")
    except Exception as e:
        logger.warning(f"user.client_id migration skipped (non-fatal): {e}")

    # Ensure credit & tax columns exist in client table
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE client ADD COLUMN IF NOT EXISTS credit_limit NUMERIC(12, 2)"))
            conn.execute(text("ALTER TABLE client ADD COLUMN IF NOT EXISTS credit_enabled BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE client ADD COLUMN IF NOT EXISTS razon_social VARCHAR"))
            conn.execute(text("ALTER TABLE client ADD COLUMN IF NOT EXISTS cuit VARCHAR"))
            conn.execute(text("ALTER TABLE client ADD COLUMN IF NOT EXISTS iva_category VARCHAR"))
            conn.execute(text("ALTER TABLE client ADD COLUMN IF NOT EXISTS transport_name VARCHAR"))
            conn.execute(text("ALTER TABLE client ADD COLUMN IF NOT EXISTS transport_address VARCHAR"))
            conn.execute(text("ALTER TABLE client ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE client ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE"))
            conn.commit()
        logger.info("client table columns ensured.")
    except Exception as e:
        logger.warning(f"client columns migration skipped (non-fatal): {e}")




    try:
        with Session(engine) as session:
            try:
                AuthService.create_default_user_and_settings(session)
            except Exception as e:
                session.rollback()
                logger.error(f"AuthService setup failed (non-fatal): {e}")
            if os.getenv("SEED_ON_START") == "1":
                seed_products(session)
    except Exception as e:
        logger.error(f"Session setup failed (non-fatal): {e}")

    # Start background daily theme scheduler
    try:
        import asyncio
        from web.scheduler import theme_scheduler_loop
        asyncio.ensure_future(theme_scheduler_loop())
        logger.info("Theme scheduler started.")
    except Exception as e:
        logger.error(f"Theme scheduler failed to start (non-fatal): {e}")

    yield


try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    limiter = Limiter(key_func=get_remote_address, default_limits=[os.getenv("RATE_LIMIT_PUBLIC", "30/minute")])
    HAS_SLOWAPI = True
except ImportError:
    limiter = None
    HAS_SLOWAPI = False

app = FastAPI(title="VibeCloud Cloud", lifespan=lifespan)
if HAS_SLOWAPI:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# CORS
def _get_cors_origins() -> list[str]:
    env = os.getenv("ENVIRONMENT", "development").lower()
    raw = os.getenv("CORS_ORIGINS", "")
    if not raw:
        if env == "production":
            raw = "https://vibecloud-frontend.onrender.com,https://vibecloud.onrender.com"
        else:
            raw = "http://localhost,http://127.0.0.1,https://vibecloud-frontend.onrender.com"
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if env == "production":
        unsafe = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
        if unsafe:
            logger.warning(f"ADVERTENCIA DE SEGURIDAD: Orígenes no seguros detectados en CORS_ORIGINS en producción: {unsafe}")
    return origins

app.add_middleware(CORSMiddleware, allow_origins=_get_cors_origins(), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


from starlette.middleware.sessions import SessionMiddleware
SESSION_SECRET = os.getenv("SECRET_KEY")
if not SESSION_SECRET:
    raise ValueError("SECRET_KEY es obligatoria en producción para SessionMiddleware.")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")


app.mount("/static", StaticFiles(directory="static"), name="static")

# Register all routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(products_router)
app.include_router(sales_router)
app.include_router(clients_router)
app.include_router(suppliers_router)
app.include_router(cash_router)
app.include_router(reports_router)
app.include_router(picking_router)
app.include_router(wms_router)

# Register API V1 Routers
app.include_router(auth_v1_router, prefix="/api/v1", tags=["Auth V1"])
app.include_router(products_v1_router, prefix="/api/v1", tags=["Products V1"])
app.include_router(sales_v1_router, prefix="/api/v1", tags=["Sales V1"])
app.include_router(ui_config_v1_router, prefix="/api/v1/ui-config", tags=["UI Config V1"])
app.include_router(ui_config_v1_router, prefix="/api/v1", tags=["UI Config V1 (Legacy)"], deprecated=True)
app.include_router(inventory_v1_router, prefix="/api/v1/inventory", tags=["Inventory V1"])
app.include_router(medusa_sync_v1_router, prefix="/api/v1", tags=["Medusa Sync V1"])



app.include_router(ai_router)
app.include_router(store_router)
app.include_router(superadmin_router)


@app.get("/health")
@app.head("/health")
async def health_check(session: Session = Depends(get_session)):
    status = "healthy"
    services = {"database": "ok"}
    try:
        session.execute(text("SELECT 1"))
    except Exception as e:
        status = "degraded"
        services["database"] = f"error: {str(e)}"
        
    return {"status": status, "services": services}


@app.get("/fix-db")
def fix_db(session: Session = Depends(get_session), user: User = Depends(require_auth)):
    if user.role != "superadmin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden: Requires superadmin role.")
    results = []
    stmts = [
        "ALTER TABLE bin ADD COLUMN IF NOT EXISTS max_capacity INTEGER",
        "ALTER TABLE bin ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE bin ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
        "ALTER TABLE binstock ADD COLUMN IF NOT EXISTS tenant_id INTEGER",
        "ALTER TABLE binstock ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
        "ALTER TABLE stockmovement ADD COLUMN IF NOT EXISTS tenant_id INTEGER",
        "ALTER TABLE stockmovement ADD COLUMN IF NOT EXISTS request_id VARCHAR",
        "ALTER TABLE stockmovement ADD COLUMN IF NOT EXISTS user_id INTEGER",
        "ALTER TABLE cashmovement ADD COLUMN IF NOT EXISTS reference_id INTEGER",
        "ALTER TABLE cashmovement ADD COLUMN IF NOT EXISTS reference_type VARCHAR",
        "ALTER TABLE cashmovement ADD COLUMN IF NOT EXISTS user_id INTEGER",
        "ALTER TABLE cashmovement ADD COLUMN IF NOT EXISTS sale_id INTEGER",
        "ALTER TABLE cashmovement ADD COLUMN IF NOT EXISTS purchase_id INTEGER",
        "ALTER TABLE payment ADD COLUMN IF NOT EXISTS receivable_id INTEGER",
        "ALTER TABLE payment ADD COLUMN IF NOT EXISTS method VARCHAR DEFAULT 'cash'",
        "ALTER TABLE product ADD COLUMN IF NOT EXISTS price_bulk FLOAT",
        "ALTER TABLE product ADD COLUMN IF NOT EXISTS price_retail FLOAT",
        "ALTER TABLE product ADD COLUMN IF NOT EXISTS cant_bulto INTEGER",
        "ALTER TABLE product ADD COLUMN IF NOT EXISTS numeracion VARCHAR",
        "ALTER TABLE product ADD COLUMN IF NOT EXISTS curve_quantity INTEGER DEFAULT 1",
        "ALTER TABLE product ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE product ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
        "ALTER TABLE product ADD COLUMN IF NOT EXISTS item_number VARCHAR",
        "ALTER TABLE product ADD COLUMN IF NOT EXISTS image_url VARCHAR",
        "ALTER TABLE supplier ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE supplier ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
        "ALTER TABLE purchase ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE purchase ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
        "ALTER TABLE location ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE location ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
        "ALTER TABLE client ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE client ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
        "ALTER TABLE client ADD COLUMN IF NOT EXISTS credit_limit FLOAT",
        "ALTER TABLE client ADD COLUMN IF NOT EXISTS razon_social VARCHAR",
        "ALTER TABLE client ADD COLUMN IF NOT EXISTS cuit VARCHAR",
        "ALTER TABLE client ADD COLUMN IF NOT EXISTS iva_category VARCHAR",
        "ALTER TABLE client ADD COLUMN IF NOT EXISTS transport_name VARCHAR",
        "ALTER TABLE client ADD COLUMN IF NOT EXISTS transport_address VARCHAR",
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS ui_theme VARCHAR DEFAULT 'default'",
        "ALTER TABLE aicredential ADD COLUMN IF NOT EXISTS api_key_enc VARCHAR",
        "ALTER TABLE businessconfig ADD COLUMN IF NOT EXISTS openai_api_key_enc VARCHAR",
        "ALTER TABLE businessconfig ADD COLUMN IF NOT EXISTS deepseek_api_key_enc VARCHAR",
        "ALTER TABLE businessconfig ADD COLUMN IF NOT EXISTS elevenlabs_api_key_enc VARCHAR",
    ]
    for stmt in stmts:
        try:
            session.exec(text(stmt))
            session.commit()
            results.append({"stmt": stmt, "status": "success"})
        except Exception as e:
            session.rollback()
            results.append({"stmt": stmt, "status": "error", "message": str(e)})
            
    # Try Alembic manually
    try:
        from alembic import command
        from alembic.config import Config
        alembic_cfg = Config("alembic.ini")
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")
        results.append({"stmt": "alembic upgrade head", "status": "success"})
    except Exception as e:
        results.append({"stmt": "alembic upgrade head", "status": "error", "message": str(e)})
        
    return {"results": results}


@app.get("/", response_class=HTMLResponse)
@app.head("/")
def get_dashboard(request: Request, user: User = Depends(require_auth), settings: Settings = Depends(get_settings), tenant_id: int = Depends(get_tenant), session: Session = Depends(get_session)):
    if user.role == "superadmin":
        return RedirectResponse("/tenants", status_code=302)
    total_products = session.exec(select(func.count(Product.id)).where(Product.tenant_id == tenant_id)).one()
    from database.models import BinStock
    from sqlalchemy.sql.functions import coalesce

    subquery = (
        select(Product.id)
        .join(BinStock, BinStock.product_id == Product.id, isouter=True)
        .where(Product.tenant_id == tenant_id, Product.is_deleted == False)
        .group_by(Product.id, Product.min_stock_level)
        .having(coalesce(func.sum(BinStock.quantity), 0) < Product.min_stock_level)
        .subquery()
    )
    low_stock = session.exec(select(func.count()).select_from(subquery)).one()
            
    recent_sales = session.exec(select(Sale).where(Sale.tenant_id == tenant_id, Sale.is_closed == False).order_by(Sale.timestamp.desc()).limit(5)).all()
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_sales_total = session.exec(select(func.sum(Sale.total_amount)).where(Sale.tenant_id == tenant_id, Sale.timestamp >= today_start, Sale.is_closed == False)).one() or 0.0
    return templates.TemplateResponse("dashboard.html", {"request": request, "active_page": "home", "settings": settings, "user": user, "total_products": total_products, "low_stock": low_stock, "recent_sales": recent_sales, "today_sales_total": today_sales_total})


@app.get("/pos", response_class=HTMLResponse)
def get_pos(request: Request, user: User = Depends(require_auth), settings: Settings = Depends(get_settings)):
    return templates.TemplateResponse("pos.html", {"request": request, "active_page": "pos", "settings": settings, "user": user})

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    with open('crash.log', 'w') as f:
        f.write(traceback.format_exc())
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(str(exc), status_code=500)
