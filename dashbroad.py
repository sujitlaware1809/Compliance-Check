# dashbroad.py - COMPLETE, FINAL, AND CORRECTED CODE (FIXED HASHING TYPO)

import streamlit as st
import pandas as pd
import sqlite3
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import re
import os
import requests 
from bs4 import BeautifulSoup 
from datetime import datetime
import hashlib
import io
import base64
import time 
from pyzbar.pyzbar import decode
import numpy as np

# Attempt to import Selenium components with error handling
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
except Exception:
    SELENIUM_AVAILABLE = False


# ---------- CONFIG & CONSTANTS ----------
# Tesseract path (Windows example) - Must be correct for the environment
try:
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
except Exception:
    pass 

DB_PATH = "product_compliance.db"
CSV_FILE = "product_compliance_records.csv"
PRODUCTS_CSV = "products.csv" # Placeholder for local barcode lookup
DISPLAY_COLUMNS = "id, user_id, username, source_type, product_name, net_weight, mrp, inclusive_of_all_taxes, mfg_date, country_of_origin, manufacturer, compliance_status, created_at"

# Streamlit-specific CSS for a cleaner look
ST_CSS = """
<style>
.main .block-container {
    padding-top: 2rem;
    padding-right: 2rem;
    padding-left: 2rem;
    padding-bottom: 2rem;
}
h3 {
    border-bottom: 2px solid #f0f2f6;
    padding-bottom: 5px;
    margin-top: 1.5rem;
}
</style>
"""
# ----------------------------------------


# ---------- UTILITIES ----------
def hash_password(password: str) -> str:
    # FIX: Corrected typo from .heghexdigest() to .hexdigest()
    return hashlib.sha256(password.encode()).hexdigest()

def init_storage():
    """Initializes SQLite database tables and seeds demo users."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Users Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT,
            fullname TEXT
        )
    ''')
    # Records Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            source_type TEXT,
            raw_text TEXT,
            product_name TEXT,
            net_weight TEXT,
            mrp TEXT,
            inclusive_of_all_taxes INTEGER,
            mfg_date TEXT,
            country_of_origin TEXT,
            manufacturer TEXT,
            compliance_status TEXT,
            created_at TEXT
        )
    ''')
    # --- COMPLAINTS TABLE (FIXED SCHEMA) ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            product_name TEXT,
            mrp TEXT,
            net_quantity TEXT,
            purchased_platform TEXT,
            date_of_order TEXT,
            date_of_delivery TEXT,
            issue_description TEXT,
            status TEXT,
            filed_at TEXT
        )
    ''')
    # ------------------------------------------
    conn.commit()

    # Seed users if not present
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        users = [
            ("officer", hash_password("officerpass"), "OFFICER", "Compliance Officer"),
            ("user", hash_password("userpass"), "USER", "Consumer User"),
        ]
        c.executemany("INSERT INTO users (username, password_hash, role, fullname) VALUES (?,?,?,?)", users)
        conn.commit()
    conn.close()

    # CSV init (keeps compatibility)
    if not os.path.exists(CSV_FILE):
        pd.DataFrame(columns=[
            "id", "user_id", "username", "source_type", "product_name", "net_weight", "mrp",
            "inclusive_of_all_taxes", "mfg_date", "country_of_origin", "manufacturer", "compliance_status", "created_at"
        ]).to_csv(CSV_FILE, index=False)

def save_record(details: dict, user):
    """Saves a compliance record to both DB and CSV."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO records (
            user_id, username, source_type, raw_text, product_name, net_weight, mrp,
            inclusive_of_all_taxes, mfg_date, country_of_origin, manufacturer, compliance_status, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        user.get('id') if user else None,
        user.get('username') if user else None,
        details.get('source_type'),
        details.get('raw_text'),
        details.get('product_name'),
        details.get('net_weight'),
        details.get('mrp'),
        1 if details.get('inclusive_of_all_taxes') else 0,
        details.get('mfg_date'),
        details.get('country_of_origin'),
        details.get('manufacturer'),
        details.get('compliance_status'),
        details.get('created_at'),
    ))
    conn.commit()
    last_id = c.lastrowid
    conn.close()
    
    row = {
        "id": last_id,
        "user_id": user.get('id') if user else None,
        "username": user.get('username') if user else None,
        "source_type": details.get('source_type'),
        "product_name": details.get('product_name'),
        "net_weight": details.get('net_weight'),
        "mrp": details.get('mrp'),
        "inclusive_of_all_taxes": 1 if details.get('inclusive_of_all_taxes') else 0,
        "mfg_date": details.get('mfg_date'),
        "country_of_origin": details.get('country_of_origin'),
        "manufacturer": details.get('manufacturer'),
        "compliance_status": details.get('compliance_status'),
        "created_at": details.get('created_at'),
    }
    try:
        df_existing = pd.read_csv(CSV_FILE)
    except FileNotFoundError:
        df_existing = pd.DataFrame(columns=row.keys())

    df_existing = pd.concat([df_existing, pd.DataFrame([row])], ignore_index=True)
    df_existing.to_csv(CSV_FILE, index=False)
    
    return last_id

def generate_label_image(product_name, mrp, net_weight, manufacturer, date_of_manufacture, country_of_origin):
    """Generates a professional-looking PNG label."""
    W, H = (650, 400)
    img = Image.new('RGB', (W, H), color='#f0f0f0')
    d = ImageDraw.Draw(img)
    
    try:
        font_title = ImageFont.truetype('arial.ttf', 24)
        font_body = ImageFont.truetype('arial.ttf', 18)
        font_mrp = ImageFont.truetype('arial.ttf', 28)
    except Exception:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_mrp = ImageFont.load_default()
        
    # REMOVED: d.text((30, 20), "PRODUCT COMPLIANCE LABEL", fill=(0, 0, 139), font=font_title)
    # REMOVED: d.line([(30, 60), (W-30, 60)], fill=(0, 0, 139), width=2)
    y_start = 20 # Adjusted starting position up since title is gone
        
    lines = [
        ("Product Name:", product_name, font_body),
        ("Manufacturer:", manufacturer, font_body),
        ("Country of Origin:", country_of_origin, font_body),
    ]
    
    y = y_start
    for label, value, font in lines:
        d.text((30, y), label, fill=(50,50,50), font=font)
        d.text((250, y), str(value), fill=(0,0,0), font=font)
        y += 40

    d.line([(30, y+10), (W-30, y+10)], fill=(150, 150, 150), width=1)
    y += 30
    
    d.text((30, y), "NET WT/QTY:", fill=(50,50,50), font=font_mrp)
    d.text((250, y), str(net_weight), fill=(0,0,0), font=font_mrp)
    y += 50
    
    d.text((30, y), "MRP (Incl. All Taxes):", fill=(139, 0, 0), font=font_mrp)
    # CHANGED: Replaced ₹ with Rs.
    d.text((350, y), f"Rs. {mrp}", fill=(139, 0, 0), font=font_mrp)
    y += 50
    
    d.text((30, y), "MFG Date:", fill=(50,50,50), font=font_body)
    d.text((250, y), date_of_manufacture, fill=(0,0,0), font=font_body)
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf
# ---------------------------------------------

# ---------- CORE LOGIC (OCR & COMPLIANCE) ----------
def ocr_image_to_text(img: Image.Image) -> str:
    """Extracts text from an image using Tesseract."""
    try:
        text = pytesseract.image_to_string(img, config='--psm 6') 
        return text
    except Exception as e:
        st.error(f"Tesseract OCR failed. Check installation/path. Error: {e}")
        return ""

def check_compliance(raw_text: str) -> dict:
    """
    Parses raw text to extract product details and checks for mandatory label compliance.
    """
    details = {}
    details['raw_text'] = raw_text

    # Product Name
    product_match = re.search(r"(?i)(?:Product(?: Name)?|Item|Description)\s*[:\s]*\s*(.+?)(?:\n|MRP|NET|WT|WGT|Qty|Manufacturer|\Z)", raw_text, re.DOTALL)
    if product_match:
        details['product_name'] = re.sub(r'\s+', ' ', product_match.group(1).strip()).split('\n')[0]
    else:
        fallback_match = re.search(r"(?i)^[\s\W]*([A-Za-z][A-Za-z0-9 ,\-]{2,80})", raw_text, re.MULTILINE)
        details['product_name'] = fallback_match.group(1).strip() if fallback_match else None

    # Net Quantity / Weight (FIXED: Improved regex for quantity/weight capture)
    net_match = re.search(
        r"(?i)(?:NET\s*WT|NET\s*WGT|NET\s*WEIGHT|NET\s*QTY|NET|Qty|Quantity|Weight)[^\n]*?(\d+[\s\.]*\d*\s*(?:g|kg|gm|ml|l|pcs|pack|packet|units|KG))", 
        raw_text
    )
    details['net_weight'] = net_match.group(1).strip() if net_match else None

    # MRP (FIXED: Improved to robustly capture price number regardless of currency symbol or intermediate text)
    mrp_match = re.search(r"(?i)(?:MRP|Maximum\s*Retail\s*Price|Price|Rs\.?)(?:[^0-9\n]*)([\d,]*\.?\d+)", raw_text) 
    details['mrp'] = mrp_match.group(1).strip().replace(',', '') if mrp_match else None

    # Inclusive of all taxes (FIXED: Added abbreviation 'Incl.' to capture generated labels)
    details['inclusive_of_all_taxes'] = bool(re.search(r"(?i)(?:inclusive\s*of\s*all\s*taxes|Incl\.?\s*All\s*Taxes)", raw_text))

    # Manufacture Date
    mfg_match = re.search(
        r"(?i)(?:Mfg|Mfd|Manufactured\s*on|Mfg\.?|MFG\s*Date)[\s:/-]*(\d{1,4}[/.-]\d{1,4}[/.-]?\d{0,4})", 
        raw_text
    )
    details['mfg_date'] = mfg_match.group(1).strip() if mfg_match else None

    # Country of Origin
    country_match = re.search(r"(?i)Country\s*of\s*Origin[:\s]*([A-Za-z\s,]+)(?:\n|Importer|Manufacturer|\Z)", raw_text)
    details['country_of_origin'] = country_match.group(1).strip() if country_match else None

    # Manufacturer/Packer/Importer Details (FIXED: Added standalone 'Manufacturer' keyword)
    manu_match = re.search(
        r"(?is)(?:Manufacturer|Manufactured\s*By|Packed\s*&\s*Marketed\s*by|Mfg\s*By|Importer|Marketer|Seller|Mfg:)\s*[:\s\-]*\s*(.+?)(?:For\s*Consumer\s*Complaints|\n{2,}|Phone:|Tel:|Email:|Customer|Net Qty|MRP|$)", 
        raw_text
    )
    if manu_match:
        manu = manu_match.group(1).strip().replace("\n", " ")
        manu = re.sub(r"\s{2,}", " ", manu)
        details['manufacturer'] = manu.split('Address:')[0].strip()
    else:
        details['manufacturer'] = None
        
    # --- COMPLIANCE CHECK ---
    
    missing = []
    if not details['product_name']: missing.append("Product Name")
    if not details['net_weight']: missing.append("Net Quantity")
    if not details['mrp']: missing.append("MRP")
    if not details['inclusive_of_all_taxes']: missing.append("Taxes Included")
    if not details['mfg_date']: missing.append("Manufacture Date")
    if not details['country_of_origin']: missing.append("Country of Origin")
    if not details['manufacturer']: missing.append("Manufacturer Details")

    details['compliance_status'] = "✅ COMPLIANT" if not missing else f"❌ NON-COMPLIANT: Missing {', '.join(missing)}"
    details['created_at'] = datetime.utcnow().isoformat()
    return details
# ---------------------------------------------


# ---------- SCRAPING (Selenium) ----------
def scrape_product(url):
    """Scrapes product details from Amazon or Flipkart using Selenium."""
    if not SELENIUM_AVAILABLE:
        raise EnvironmentError("Selenium is not available for URL scraping.")

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
    except Exception:
        raise EnvironmentError("Chromedriver/Chrome setup failed. Ensure Chrome and Chromedriver are installed and in PATH.")


    driver.get(url)
    time.sleep(3) 

    product = {"url": url, "Product name": None, "MRP": None, "Net Quantity": None, "Brand name (Proxy)": None, "Manufacturer details": None}
    raw_text = ""
    page_text = driver.page_source
    
    if "amazon" in url:
        try:
            product["Product name"] = driver.find_element(By.ID, "productTitle").text.strip()
            
            try:
                brand_element = driver.find_element(By.ID, "bylineInfo")
                brand_text = brand_element.text.strip()
                brand_name_match = re.search(r'(?i)(?:Visit\s*the\s*|Store\s*|Brand:\s*)?(.+)', brand_text)
                if brand_name_match:
                     product["Brand name (Proxy)"] = brand_name_match.group(1).strip()
            except:
                pass 
                
            price_element = driver.find_element(By.XPATH, "//span[@class='a-price-whole']")
            product["MRP"] = price_element.text.strip() if price_element else None
            qty_match = re.search(r'(\d+\s*(g|ml|kg|L|pcs))', page_text, re.IGNORECASE)
            product["Net Quantity"] = qty_match.group(0) if qty_match else None
        except Exception:
            pass
            
    elif "flipkart" in url:
        try:
            product["Product name"] = driver.find_element(By.CLASS_NAME, "B_NuCI").text.strip()
            
            try:
                brand_element = driver.find_element(By.CLASS_NAME, "G6XhRU") 
                product["Brand name (Proxy)"] = brand_element.text.strip() if brand_element else None
            except:
                pass
            price_element = driver.find_element(By.CLASS_NAME, "_30jeq3")
            product["MRP"] = price_element.text.strip() if price_element else None
            qty_match = re.search(r'(\d+\s*(g|ml|kg|L|pcs))', page_text, re.IGNORECASE)
            product["Net Quantity"] = qty_match.group(0) if qty_match else None
        except Exception:
            pass
            
    else:
        driver.quit()
        raise ValueError("Unsupported website. Only Amazon/Flipkart links supported via Selenium.")

    manu_match = re.search(
        r"(?is)(?:Manufactured\s*By|Packed\s*By|Importer|Marketer|Seller|Address|Marketed\s*By)\s*[:\s\-]*\s*(.+?)(?:\s{2,}|<br>|<BR>|<div|<span|</p>|\Z)", 
        page_text
    )
    
    if manu_match:
        manu_detail = manu_match.group(1).strip()
        soup_snippet = BeautifulSoup(manu_detail, 'html.parser')
        cleaned_text = soup_snippet.get_text(strip=True).replace('\n', ' ')
        
        # --- FIX: Aggressive cleanup to remove embedded URL/JSON snippets ---
        cleaned_text = re.sub(r'[<>"{}|\\\/]', ' ', cleaned_text)
        cleaned_text = re.sub(r'selections\?deviceType=.+modal', '', cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r'\s{2,}', ' ', cleaned_text).strip()
        # ------------------------------------------------------------------
        
        product["Manufacturer details"] = cleaned_text[:200]
        
    # LOGIC ALREADY PRESENT: Manufacturer details defaults to Brand name if detailed match is not found
    if not product["Manufacturer details"] and product["Brand name (Proxy)"]:
        product["Manufacturer details"] = product["Brand name (Proxy)"]
        
    raw_text += f"Product Name: {product.get('Product name') or ''}\n"
    raw_text += f"MRP: Rs {product.get('MRP') or ''} (Inclusive of all taxes)\n" 
    raw_text += f"Net Quantity: {product.get('Net Quantity') or ''}\n"
    
    if product["Manufacturer details"]:
        raw_text += f"Manufacturer: {product['Manufacturer details']}\n"
    
    driver.quit()
    
    return raw_text, product


# ---------- BARCODE FUNCTIONS ----------

def decode_barcode(image):
    """Decode barcodes from an image object."""
    if image.mode != 'RGB':
        image = image.convert('RGB')
    return decode(image)

def fetch_from_api(barcode_data):
    """Fetch product from OpenFoodFacts API."""
    barcode_data = re.sub(r'\D', '', barcode_data)
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode_data}.json"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("status") == 1:
            product = data["product"]
            return {
                "Product Name": product.get("product_name", "N/A"),
                "Brand": product.get("brands", "N/A"),
                "Quantity": product.get("quantity", "N/A"),
                "Manufacturer": product.get("manufacturing_places", product.get("brands", "N/A")),
                "Country": product.get("countries", "N/A"),
                "MRP": "N/A (API)", 
                "MFG Date": "N/A (API)"
            }
    except Exception:
        pass
    return None

def fetch_from_local_db(barcode_data):
    """Fallback: check local CSV database."""
    try:
        df = pd.read_csv(PRODUCTS_CSV)
        row = df[df["barcode"].astype(str) == str(barcode_data)]
        if not row.empty:
            record = row.iloc[0].to_dict()
            return {
                "Product Name": record.get("product_name", "N/A"),
                "Brand": record.get("brand", "N/A"),
                "Quantity": record.get("quantity", "N/A"),
                "Manufacturer": record.get("manufacturer", "N/A"),
                "Country": record.get("country", "N/A"),
                "MRP": record.get("mrp", "N/A"),
                "MFG Date": record.get("mfg_date", "N/A")
            }
    except FileNotFoundError:
        pass
    return None

def get_product_details(barcode_data):
    """Coordinates lookup from API and local DB."""
    details = fetch_from_api(barcode_data)
    if details and details.get("Product Name") != "N/A":
        return details
        
    details = fetch_from_local_db(barcode_data)
    if details:
        return details
        
    return {"Error": "❌ Product details not found from API or Local DB", "Barcode": barcode_data}

def process_barcode_compliance(details: dict, source_type: str):
    """
    Constructs raw_text from barcode details, runs compliance check, saves, and displays.
    It then merges non-'N/A' data from the API back into the compliance results.
    """
    raw_text = ""
    product_name_api = details.get('Product Name', 'N/A')
    manu_detail_api = details.get('Manufacturer', details.get('Brand', 'N/A'))
    net_qty_api = details.get('Quantity', 'N/A')
    mrp_api = details.get('MRP', 'N/A')
    mfg_date_api = details.get('MFG Date', 'N/A')
    country_api = details.get('Country', 'N/A')
    
    raw_text += f"Product Name: {product_name_api}\n"
    raw_text += f"Manufacturer: {manu_detail_api}\n"
    raw_text += f"Net Quantity: {net_qty_api}\n"
    if mrp_api != 'N/A (API)':
        raw_text += f"MRP: {mrp_api} (Inclusive of all taxes)\n" 
    else:
        raw_text += f"MRP: {mrp_api}\n" 
    raw_text += f"MFG Date: {mfg_date_api}\n"
    raw_text += f"Country of Origin: {country_api}\n"
    
    compliance_details = check_compliance(raw_text)
    compliance_details['source_type'] = source_type

    # --- ENHANCEMENT: OVERRIDE compliance_details with non-N/A API data ---
    
    # 1. Product Name
    if compliance_details.get('product_name') in [None, 'N/A'] and product_name_api not in ['N/A', None]:
        compliance_details['product_name'] = product_name_api
        
    # 2. Net Quantity
    if compliance_details.get('net_weight') in [None, 'N/A'] and net_qty_api not in ['N/A', None, '']:
        compliance_details['net_weight'] = net_qty_api
        
    # 3. MRP
    if compliance_details.get('mrp') in [None, 'N/A'] and mrp_api not in ['N/A', 'N/A (API)', None]:
        mrp_val = str(mrp_api).replace('Rs.', '').replace('₹', '').strip()
        compliance_details['mrp'] = mrp_val
        
    # 4. Manufacturer
    if compliance_details.get('manufacturer') in [None, 'N/A'] and manu_detail_api not in ['N/A', None, '']:
        compliance_details['manufacturer'] = manu_detail_api
    
    # 5. Country of Origin (Clean up 'en:' prefixes from OpenFoodFacts)
    if compliance_details.get('country_of_origin') in [None, 'N/A'] and country_api not in ['N/A', None]:
        country = str(country_api).replace('en:', '').replace('es:', '').replace('fr:', '').split(',')[0].strip()
        compliance_details['country_of_origin'] = country
        
    # 6. MFG Date (If API returned a value but regex missed it)
    if compliance_details.get('mfg_date') in [None, 'N/A'] and mfg_date_api not in ['N/A', 'N/A (API)', None]:
        compliance_details['mfg_date'] = mfg_date_api
    # ------------------------------------------------------------------------

    # Re-check compliance status after overriding critical fields
    missing = []
    # Note: MRP/MFG Date are often missing from APIs, so we use the final value
    if not compliance_details['product_name'] or compliance_details['product_name'] == 'N/A': missing.append("Product Name")
    if not compliance_details['net_weight'] or compliance_details['net_weight'] == 'N/A': missing.append("Net Quantity")
    if not compliance_details['mrp'] or compliance_details['mrp'] in ['N/A', 'N/A (API)']: missing.append("MRP")
    if not compliance_details['inclusive_of_all_taxes']: missing.append("Taxes Included (Assumed Missing)")
    if not compliance_details['mfg_date'] or compliance_details['mfg_date'] == 'N/A': missing.append("Manufacture Date")
    if not compliance_details['country_of_origin'] or compliance_details['country_of_origin'] == 'N/A': missing.append("Country of Origin")
    if not compliance_details['manufacturer'] or compliance_details['manufacturer'] == 'N/A': missing.append("Manufacturer Details")
    
    # Update final compliance status
    compliance_details['compliance_status'] = "✅ COMPLIANT" if not missing else f"❌ NON-COMPLIANT: Missing {', '.join(missing)}"
    
    
    display_compliance_report(compliance_details)
    
    user = st.session_state.get('user')
    if user:
        save_record(compliance_details, user)
        st.success(f"Compliance record saved for ID: **{compliance_details.get('product_name', 'Product')}**.")

# ---------------------------------------------

# ---------- PROFESSIONAL UI COMPONENTS ----------

def display_compliance_report(details: dict):
    """Displays the professional compliance report."""
    st.subheader("Compliance Report & Extracted Details")
    
    with st.container(border=True):
        
        status_value = details['compliance_status']
        if "COMPLIANT" in status_value:
            st.success(f"**{status_value}**")
        else:
            st.error(f"**{status_value}**")

        st.markdown("---")
        
        st.info("🎯 **Key Product Information Extracted**")
        
        colA, colB, colC = st.columns(3)
        
        colA.metric(
            label="📦 Product Name",
            value=details.get('product_name', 'N/A')
        )
        colA.metric(
            label="⚖️ Net Weight/Quantity",
            value=details.get('net_weight', 'N/A')
        )
        
        colB.metric(
            label="💲 Maximum Retail Price (MRP)",
            value=f"Rs. {details.get('mrp', 'N/A')}" # Updated display to match Rs.
        )
        colB.metric(
            label="🧾 Taxes Included?",
            value=('✅ Yes' if details.get('inclusive_of_all_taxes') else '❌ No')
        )
        
        colC.metric(
            label="🌍 Country of Origin",
            value=details.get('country_of_origin', 'N/A')
        )
        colC.metric(
            label="📅 Manufacture Date",
            value=details.get('mfg_date', 'N/A')
        )
        
        st.markdown(f"**🏭 Manufacturer/Importer Details:** {details.get('manufacturer', 'N/A')}")
        
        with st.expander("🛠️ Show Technical Details (Raw Text Analysis)"):
            st.text_area("Extracted Text (Used for Regex Analysis)", details['raw_text'], height=150)
            st.subheader("Full JSON Result")
            st.json(details)

def barcode_scanner_ui():
    """UI for all barcode related inputs and processing. (FIXED TUPLE ERROR)"""
    st.subheader("📦 Barcode Product Lookup (EAN/UPC)")
    st.caption("Scans or takes manual input for barcode lookup via OpenFoodFacts API or local database.")

    with st.container(border=True):
        option = st.radio(
            "Choose Barcode Input Method:",
            ["1. Upload Image", "2. Camera Scan", "3. Manual Entry"],
            horizontal=True
        )

        st.markdown("---")
        
        barcode_processed = False
        
        if option == "1. Upload Image":
            uploaded_file = st.file_uploader("Upload Barcode Image", type=["jpg", "jpeg", "png"])
            if uploaded_file:
                try:
                    image = Image.open(uploaded_file)
                    st.image(image, caption="Uploaded Image", use_container_width=True)
                    results = decode_barcode(image)
                    if results:
                        # FIX: Using attribute access (.data, .type) on the Decoded object
                        first_barcode = results[0]
                        st.success(f"✅ Barcode detected ({first_barcode.type}). Fetching details...")
                        process_barcode_lookup(
                            first_barcode.data.decode("utf-8"), 
                            source_type=f"Barcode Scan ({first_barcode.type})"
                        )
                        barcode_processed = True
                    else:
                        st.error("❌ No barcode detected in the image.")
                except Exception as e:
                    st.error(f"Error processing uploaded image: {e}")

        elif option == "2. Camera Scan":
            camera_img = st.camera_input("Capture Barcode Image")
            if camera_img:
                try:
                    image = Image.open(camera_img)
                    results = decode_barcode(image)
                    if results:
                        # FIX: Using attribute access (.data, .type) on the Decoded object
                        first_barcode = results[0]
                        st.success(f"✅ Barcode detected ({first_barcode.type}). Fetching details...")
                        process_barcode_lookup(
                            first_barcode.data.decode("utf-8"), 
                            source_type=f"Barcode Camera Scan ({first_barcode.type})"
                        )
                        barcode_processed = True
                    else:
                        st.error("❌ No barcode detected in the image.")
                except Exception as e:
                    st.error(f"Error processing camera image: {e}")

        elif option == "3. Manual Entry":
            barcode_input = st.text_input("Enter Barcode Number (e.g., EAN-13, UPC)")
            if barcode_input and st.button("Lookup Barcode Details", use_container_width=True):
                process_barcode_lookup(barcode_input.strip(), source_type="Barcode Manual Entry")
                barcode_processed = True
        
        if not barcode_processed:
            st.info("Awaiting barcode input to run compliance check.")

def process_barcode_lookup(barcode_data: str, source_type: str):
    """Wrapper function to handle barcode data and call compliance process."""
    details = get_product_details(barcode_data)
    if "Error" not in details:
        process_barcode_compliance(details, source_type)
    else:
        st.error(details["Error"])

def complaint_register_ui():
    st.subheader("📝 Register a Product Complaint")
    st.caption("Report issues regarding labeling, quality, or delivery.")

    user = st.session_state.get('user')
    if not user:
        st.error("You must be logged in to register a complaint.")
        return

    with st.form("complaint_form", clear_on_submit=True):
        st.markdown("**Product Details**")
        col1, col2 = st.columns(2)
        
        product_name = col1.text_input("Product Name*")
        mrp = col2.text_input("MRP / Price (₹)")
        net_quantity = col1.text_input("Net Weight / Quantity")
        purchased_platform = col2.selectbox("Purchased Platform*", 
                                            ['Amazon', 'Flipkart', 'Other E-Commerce', 'Retail Store', 'Direct from Seller'])

        st.markdown("---")
        st.markdown("**Order & Issue Details**")
        
        col3, col4 = st.columns(2)
        date_of_order = col3.date_input("Date of Order", max_value=datetime.today(), value=None)
        date_of_delivery = col4.date_input("Date of Delivery", max_value=datetime.today(), value=None)
        
        issue_description = st.text_area("Details / Description of Issue*", height=150, help="Please describe the issue clearly.")
        
        st.markdown("---")
        
        submitted = st.form_submit_button("Submit Complaint to Officer", type="primary", use_container_width=True)

        if submitted:
            if not all([product_name, purchased_platform, issue_description]):
                st.error("Please fill in all mandatory fields (*).")
            else:
                try:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    
                    c.execute('''
                        INSERT INTO complaints (
                            user_id, username, product_name, mrp, net_quantity, 
                            purchased_platform, date_of_order, date_of_delivery, 
                            issue_description, status, filed_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    ''', (
                        user['id'], 
                        user['username'], 
                        product_name, 
                        mrp, 
                        net_quantity,
                        purchased_platform, 
                        date_of_order.isoformat() if date_of_order else None,
                        date_of_delivery.isoformat() if date_of_delivery else None,
                        issue_description, 
                        "New", # Default status
                        datetime.utcnow().isoformat()
                    ))
                    conn.commit()
                    conn.close()
                    st.success("✅ Complaint Registered Successfully! The Compliance Officer will review it shortly.")
                    st.balloons()
                except Exception as e:
                    st.error(f"An error occurred while saving the complaint. Check DB schema. Error: {e}")
# ---------------------------------------------


# ---------- DASHBOARD VIEWS ----------

def officer_dashboard():
    st.header("OFFICER Compliance Management Dashboard")
    
    tabs = st.tabs(["🖼️ OCR / Web Check", "📦 Barcode Scan", "📊 Records Log", "🏷️ Generate Label", "⬇️ Export Data", "🚨 Complaints Tracker"])
    
    # ----------------------------------------
    # UPLOAD & CHECK TAB (Tab 0: OCR / Web)
    # ----------------------------------------
    with tabs[0]:
        st.subheader("1. Source Input for Compliance Check")

        source_options = ['Upload Image', 'Camera Capture']
        if SELENIUM_AVAILABLE:
            source_options.append('Product URL Scrape (Amazon/Flipkart)')
            
        with st.container(border=True):
            source_selection = st.radio("Input Type:", source_options, index=0, horizontal=True)

            uploaded_file = None
            camera_img = None
            url = None
            
            if source_selection == 'Upload Image':
                uploaded_file = st.file_uploader("Upload an image of the label", type=['png','jpg','jpeg'])
            elif source_selection == 'Camera Capture':
                camera_img = st.camera_input("Capture image of the label")
            elif source_selection == 'Product URL Scrape (Amazon/Flipkart)':
                url = st.text_input("Amazon or Flipkart Product URL:")
            
            check_btn = st.button("Process Compliance Check (OCR/Web)", use_container_width=True)

        if check_btn:
            raw_text = ""
            source_type = None

            if camera_img:
                img = Image.open(camera_img)
                raw_text = ocr_image_to_text(img)
                source_type = "Camera OCR"
            elif uploaded_file:
                img = Image.open(uploaded_file)
                raw_text = ocr_image_to_text(img)
                source_type = "Uploaded Image OCR"
            elif url and source_selection == 'Product URL Scrape (Amazon/Flipkart)':
                with st.spinner("Scraping product details..."):
                    try:
                        raw_text, product_details_scraped = scrape_product(url)
                        source_type = "Product URL (Selenium)"
                        # st.json(product_details_scraped) # Removed redundant output
                    except Exception as e:
                        st.error(f"Error fetching/scrolling/scraping URL. Error: {e}")
                        raw_text = ""
                        source_type = "Product URL (error)"

            if raw_text and source_type not in ["Product URL (error)"]:
                details = check_compliance(raw_text)
                details['source_type'] = source_type
                display_compliance_report(details)
                
                user = st.session_state.get('user')
                save_record(details, user)
                st.success(f"Compliance record saved for: **{details.get('product_name', 'Product')}**.")
            else:
                st.info("Processing complete with no valid text extracted.")

    # ----------------------------------------
    # BARCODE SCAN TAB (Tab 1)
    # ----------------------------------------
    with tabs[1]:
        barcode_scanner_ui()

    # ----------------------------------------
    # RECORDS TAB (Tab 2)
    # ----------------------------------------
    with tabs[2]:
        st.subheader("All Compliance Records Log")
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(f"SELECT {DISPLAY_COLUMNS} FROM records ORDER BY created_at DESC", conn)
        conn.close()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No records yet.")

    # ----------------------------------------
    # GENERATE LABEL TAB (Tab 3)
    # ----------------------------------------
    with tabs[3]:
        st.subheader("Custom Label Generation Tool")
        
        if 'generated_label_buf' not in st.session_state:
            st.session_state.generated_label_buf = None
            
        with st.form("label_form"):
            col1, col2 = st.columns(2)
            product_name = col1.text_input("1. Product Name")
            mrp = col1.text_input("2. MRP / Price (e.g., 99.99)")
            net_weight = col1.text_input("3. Net Weight / Quantity (e.g., 500g)")
            manufacturer = col2.text_input("4. Manufacturer Details")
            date_of_manufacture = col2.text_input("5. Date of Manufacture (e.g., 01/2025)") 
            country_of_origin = col2.text_input("6. Country of Origin")
            
            submitted = st.form_submit_button("Generate Compliant Label", type="primary", use_container_width=True)
            
            if submitted:
                if any(not val for val in [product_name, mrp, net_weight, manufacturer, date_of_manufacture, country_of_origin]):
                    st.error("All 6 fields are required to generate a compliant label.")
                else:
                    st.session_state.generated_label_buf = generate_label_image(
                        product_name, mrp, net_weight, manufacturer, date_of_manufacture, country_of_origin
                    )
                    st.session_state.label_details = (product_name, mrp, date_of_manufacture)
                    st.success("Label image generated below. Verify details before printing.")

        if st.session_state.generated_label_buf:
            st.markdown("---")
            st.image(st.session_state.generated_label_buf, caption="Generated Label Preview", use_container_width=True)
            st.download_button(
                "📥 Download Label PNG", 
                data=st.session_state.generated_label_buf, 
                file_name=f"label_{st.session_state.label_details[0].replace(' ', '_')}.png", 
                mime="image/png",
                use_container_width=True
            )

    # ----------------------------------------
    # EXPORT CSV TAB (Tab 4)
    # ----------------------------------------
    with tabs[4]:
        st.subheader("Export Full Compliance Data")
        if os.path.exists(CSV_FILE):
            df_csv = pd.read_csv(CSV_FILE)
            st.dataframe(df_csv, use_container_width=True)
            with open(CSV_FILE, "rb") as f:
                st.download_button("Download CSV File", data=f, file_name=CSV_FILE, mime="text/csv", type="primary", use_container_width=True)
        else:
            st.warning("CSV file not found. Run a check first to create the file.")

    # ----------------------------------------
    # COMPLAINTS TRACKER TAB (Tab 5 - NEW)
    # ----------------------------------------
    with tabs[5]:
        st.subheader("🚨 Active Consumer Complaints")
        st.caption("Review and manage all complaints submitted by users.")

        conn = sqlite3.connect(DB_PATH)
        df_complaints = pd.read_sql_query("SELECT * FROM complaints ORDER BY filed_at DESC", conn)
        conn.close()

        if df_complaints.empty:
            st.info("No complaints have been registered yet.")
        else:
            df_display = df_complaints.drop(columns=['user_id', 'id', 'filed_at'])
            
            df_display.rename(columns={
                'username': 'Filed By',
                'product_name': 'Product Name',
                'net_quantity': 'Net Qty',
                'purchased_platform': 'Platform',
                'issue_description': 'Issue Description',
                'status': 'Status',
                'date_of_order': 'Order Date',
                'date_of_delivery': 'Delivery Date',
            }, inplace=True)
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.caption("Status can be managed/updated directly in the database.")


def user_dashboard():
    st.header(f"Consumer Check Panel - Welcome, {st.session_state.user.get('fullname','User')}!")
    
    tabs = st.tabs(["🖼️ OCR Check", "📦 Barcode Scan", "📋 Your Personal Log", "🚨 Complaint Register"])
    
    # ----------------------------------------
    # UPLOAD & CHECK TAB (Tab 0: OCR)
    # ----------------------------------------
    with tabs[0]:
        st.subheader("1. Source Input for Compliance Check")

        source_options = ['Upload Image', 'Camera Capture']
        if SELENIUM_AVAILABLE:
            source_options.append('Product URL Scrape (Amazon/Flipkart)')
            
        with st.container(border=True):
            source_selection = st.radio("Input Type:", source_options, index=0, horizontal=True)

            uploaded_file = None
            camera_img = None
            url = None

            if source_selection == 'Upload Image':
                uploaded_file = st.file_uploader("Upload an image of the label", type=['png','jpg','jpeg'])
            elif source_selection == 'Camera Capture':
                camera_img = st.camera_input("Capture image of the label")
            elif source_selection == 'Product URL Scrape (Amazon/Flipkart)':
                url = st.text_input("Amazon or Flipkart Product URL:")

            check_btn = st.button("Process Compliance Check (OCR/Web)", type="primary", use_container_width=True)

        if check_btn:
            raw_text = ""
            source_type = None

            if camera_img:
                img = Image.open(camera_img)
                raw_text = ocr_image_to_text(img)
                source_type = "Camera OCR"
            elif uploaded_file:
                img = Image.open(uploaded_file)
                raw_text = ocr_image_to_text(img)
                source_type = "Uploaded Image OCR"
            elif url and source_selection == 'Product URL Scrape (Amazon/Flipkart)':
                with st.spinner("Scraping product details..."):
                    try:
                        raw_text, product_details_scraped = scrape_product(url)
                        source_type = "Product URL (Selenium)"
                        # st.json(product_details_scraped) # Removed redundant output
                    except Exception as e:
                        st.error(f"Error fetching/scraping URL: {e}")
                        raw_text = ""
                        source_type = "Product URL (error)"

            if raw_text and source_type not in ["Product URL (error)"]:
                details = check_compliance(raw_text)
                details['source_type'] = source_type
                display_compliance_report(details)

                user = st.session_state.get('user')
                save_record(details, user)
                st.success("Result saved to your personal log.")
            else:
                st.info("Processing complete with no valid text extracted.")

    # ----------------------------------------
    # BARCODE SCAN TAB (Tab 1)
    # ----------------------------------------
    with tabs[1]:
        barcode_scanner_ui()

    # ----------------------------------------
    # YOUR LOG TAB (Tab 2)
    # ----------------------------------------
    with tabs[2]:
        st.subheader("Your Personal Log of Checks")
        user_id = st.session_state.user.get('id')
        conn = sqlite3.connect(DB_PATH)
        df_user = pd.read_sql_query(f"SELECT {DISPLAY_COLUMNS} FROM records WHERE user_id=? ORDER BY created_at DESC", conn, params=(user_id,))
        conn.close()
        if not df_user.empty:
            st.dataframe(df_user, use_container_width=True)
        else:
            st.info("No personal records yet. Run a check to start logging!")

    # ----------------------------------------
    # COMPLAINT REGISTER TAB (Tab 3 - NEW)
    # ----------------------------------------
    with tabs[3]: 
        complaint_register_ui()


# ---------- AUTHENTICATION & MAIN ----------

def get_user_from_db(username: str):
    """Retrieves user details from database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username, password_hash, role, fullname FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'id': row[0], 'username': row[1], 'password_hash': row[2], 'role': row[3], 'fullname': row[4]}
    return None

def authenticate(username: str, password: str):
    """Checks credentials."""
    u = get_user_from_db(username)
    if u and hash_password(password) == u['password_hash']:
        return u
    return None

def login_ui():
    """Handles login/logout in the sidebar."""
    st.sidebar.header("🔑 User Access")
    if 'user' in st.session_state:
        st.sidebar.success(f"Logged in as **{st.session_state.user['username']}** ({st.session_state.user['role']})")
        if st.sidebar.button("Logout", use_container_width=True):
            del st.session_state['user']
            st.rerun()
        return

    # Login Form
    with st.sidebar.form("login_form"):
        username = st.text_input("Username", value="")
        password = st.text_input("Password", type="password", value="")
        login_btn = st.form_submit_button("Login", type="primary", use_container_width=True)

    if login_btn:
        user = authenticate(username, password)
        if user:
            st.session_state.user = {'id': user['id'], 'username': user['username'], 'role': user['role'], 'fullname': user['fullname']}
            st.success(f"Logged in as {user['username']} ({user['role']})")
            time.sleep(0.5)
            st.rerun()
        else:
            st.sidebar.error("Invalid credentials")

    st.sidebar.markdown("---")
    st.sidebar.caption("Demo accounts:")
    st.sidebar.code("officer / officerpass (OFFICER)")
    st.sidebar.code("user / userpass (USER)")


def main():
    # Apply custom CSS
    st.set_page_config(page_title="E-Commerce Product Compliance Checker", layout="wide")
    st.markdown(ST_CSS, unsafe_allow_html=True)
    
    st.title("🇮🇳 Product Compliance Analyzer")
    st.markdown("### Powered by OCR, Web Scraping, and Barcode Lookup for Label Verification")

    # Initial setup
    init_storage()

    # Authentication on Sidebar
    login_ui()
    
    if not SELENIUM_AVAILABLE:
        st.warning("⚠️ **URL Scraping Unavailable:** Ensure the `selenium` library and a configured Chrome/Chromedriver are in your environment to use the web scraping feature.")


    if 'user' not in st.session_state:
        st.info("Please login using the sidebar to access the compliance tools.")
        return

    # Route to the appropriate dashboard
    role = st.session_state.user.get('role')
    if role == 'OFFICER':
        officer_dashboard()
    else:
        user_dashboard()

if __name__ == "__main__":
    main()