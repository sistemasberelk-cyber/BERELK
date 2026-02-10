
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from sqlmodel import Session, select, func
from database.models import Product, Sale, Client, Payment
from datetime import datetime
import os

# --- Configuration ---
# The ID of your spreadsheet (from the URL you provided)
SPREADSHEET_ID = "1oAKLT7SAVn4yfX6Jtm_LXWXS9AiYn8S-UGspV2TBW4w"
CREDENTIALS_FILE = "credentials.json"

def perform_backup(session: Session):
    """
    Connects to Google Sheets and uploads:
    1. Daily Sales (Ventas del Dia)
    2. Debtors List (Deudores)
    3. Products Stock (Stock)
    """
    print("🚀 Starting Backup Process...")
    
    # Authenticate with Google
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    try:
        # 1. Try Loading from Environment Variable (Render/Production)
        import json
        google_creds_env = os.environ.get("GOOGLE_CREDENTIALS")
        
        if google_creds_env:
            print("🔑 Loading credentials from Environment Variable...")
            creds_dict = json.loads(google_creds_env)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            # 2. Fallback to local file (Dev)
            if os.path.exists(CREDENTIALS_FILE):
                print("📂 Loading credentials from local file...")
                creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
            else:
                raise Exception("No credentials found! Set GOOGLE_CREDENTIALS env var or update credentials.json")
                
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        print(f"❌ Error authenticating with Google: {e}")
        return {"status": "error", "message": str(e)}

    # --- 1. DAILY SALES CHECK ---
    try:
        # Get or Create Worksheet
        try:
            sheet_sales = spreadsheet.worksheet("Ventas")
        except:
            sheet_sales = spreadsheet.add_worksheet(title="Ventas", rows="1000", cols="10")
            sheet_sales.append_row(["ID Venta", "Fecha", "Cliente", "Total", "Pagado", "Metodo", "Items"])

        # Fetch today's sales
        today_date = datetime.now().strftime('%Y-%m-%d')
        # In a real scenario you might want ALL sales or filtered by date. 
        # For 'Cierre de Caja', usually we want Today's summary.
        # But for 'Backup', maybe we want the latest untracked ones?
        # Let's dump the last 50 sales for now to ensure data is there.
        
        sales = session.exec(select(Sale).order_by(Sale.timestamp.desc()).limit(100)).all()
        
        # Prepare data rows
        sales_rows = []
        for s in sales:
            client_name = "Mostrador"
            if s.client_id:
                client_obj = session.get(Client, s.client_id)
                if client_obj: client_name = client_obj.name
            
            items_str = ", ".join([f"{i.quantity}x {i.product_name}" for i in s.items])
            
            sales_rows.append([
                s.id,
                s.timestamp.strftime('%Y-%m-%d %H:%M'),
                client_name,
                s.total_amount,
                s.amount_paid,
                s.payment_method,
                items_str
            ])
            
        # Clear and overwrite (simple backup strategy)
        # OR append? Overwriting 'Ventas' sheet with last 100 is safer to avoid duplicates implementation complexity now.
        sheet_sales.clear()
        sheet_sales.append_row(["ID Venta", "Fecha", "Cliente", "Total", "Pagado", "Metodo", "Items"])
        sheet_sales.append_rows(sales_rows)
        print("✅ Sales Backup Complete.")
        
    except Exception as e:
        print(f"⚠️ Error backing up Sales: {e}")

    # --- 2. DEBTORS (Cuentas Corrientes) ---
    try:
        try:
            sheet_debt = spreadsheet.worksheet("Deudores")
        except:
            sheet_debt = spreadsheet.add_worksheet(title="Deudores", rows="1000", cols="5")
            sheet_debt.append_row(["ID Cliente", "Nombre", "Telefono", "Limite Credito", "SALDO DEUDA"])

        clients = session.exec(select(Client)).all()
        debtors_rows = []
        
        total_debt_street = 0
        
        for c in clients:
            # Calculate Balance
            sales_total = session.exec(select(func.sum(Sale.total_amount)).where(Sale.client_id == c.id)).one() or 0.0
            payments_total = session.exec(select(func.sum(Payment.amount)).where(Payment.client_id == c.id)).one() or 0.0
            balance = float(sales_total - payments_total)
            
            if balance > 10: # Only list those who owe significant money
                debtors_rows.append([
                    c.id,
                    c.name,
                    c.phone,
                    c.credit_limit,
                    balance
                ])
                total_debt_street += balance
                
        sheet_debt.clear()
        sheet_debt.append_row(["ID Cliente", "Nombre", "Telefono", "Limite Credito", "SALDO DEUDA"])
        sheet_debt.append_rows(debtors_rows)
        sheet_debt.append_row(["", "", "", "TOTAL EN LA CALLE:", total_debt_street])
        
        print(f"✅ Debtors Backup Complete. Total Debt: ${total_debt_street}")

    except Exception as e:
        print(f"⚠️ Error backing up Debtors: {e}")

    # --- 3. STOCK SNAPSHOT ---
    try:
        try:
            sheet_stock = spreadsheet.worksheet("Stock")
        except:
            sheet_stock = spreadsheet.add_worksheet(title="Stock", rows="1000", cols="6")
        
        products = session.exec(select(Product)).all()
        stock_rows = []
        for p in products:
            stock_rows.append([
                p.id,
                p.item_number,
                p.name,
                p.category,
                p.stock_quantity,
                p.price
            ])
            
        sheet_stock.clear()
        sheet_stock.append_row(["ID", "Articulo", "Producto", "Categoria", "CANTIDAD", "Precio"])
        sheet_stock.append_rows(stock_rows)
        print("✅ Stock Backup Complete.")
        
    except Exception as e:
        print(f"⚠️ Error backing up Stock: {e}")

    return {"status": "success", "message": "Backup completed successfully to Google Drive"}

if __name__ == "__main__":
    # Test run
    from database.session import get_session
    session = next(get_session())
    perform_backup(session)
