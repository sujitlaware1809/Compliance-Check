import streamlit as st
import pandas as pd
from PIL import Image
import os
import platform
import subprocess
import sys

# Try importing pytesseract with error handling
try:
    import pytesseract
    st.success("✅ pytesseract imported successfully")
except ImportError as e:
    st.error(f"❌ Failed to import pytesseract: {e}")
    st.info("Attempting to install pytesseract...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pytesseract"])
        import pytesseract
        st.success("✅ pytesseract installed and imported successfully")
    except Exception as install_error:
        st.error(f"❌ Failed to install pytesseract: {install_error}")
        st.stop()

import re

# Set Tesseract path based on environment
if platform.system() == "Windows" and os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    st.info("🖥️ Running on Windows - Tesseract path set")
else:
    # For Linux/Streamlit Cloud, check if tesseract is available
    try:
        result = subprocess.run(['which', 'tesseract'], capture_output=True, text=True)
        if result.returncode == 0:
            st.info(f"🐧 Running on Linux - Tesseract found at: {result.stdout.strip()}")
        else:
            st.warning("⚠️ Tesseract not found in PATH")
    except Exception as e:
        st.warning(f"⚠️ Could not check tesseract availability: {e}")

CSV_FILE = "camera_ocr_products.csv"
if not os.path.exists(CSV_FILE):
    pd.DataFrame(columns=[
        "product_name", "net_weight", "mrp",
        "inclusive_of_all_taxes", "mfg_date",
        "country_of_origin", "manufacturer", "compliance_status"
    ]).to_csv(CSV_FILE, index=False)

st.title("📸 Product Label OCR & Compliance Checker")

# --- Choose Input Method ---
st.subheader("Upload or Capture Product Label")
input_option = st.radio("Select input method:", ["📷 Camera", "📂 Upload Image"])

picture = None
if input_option == "📷 Camera":
    picture = st.camera_input("Take a photo of the product label")
elif input_option == "📂 Upload Image":
    picture = st.file_uploader("Upload a product label image", type=["jpg", "jpeg", "png"])

if picture:
    img = Image.open(picture)

    # OCR text
    raw_text = pytesseract.image_to_string(img)
    st.text_area("🔎 Raw OCR Output", raw_text, height=200)

    # --- Extract fields ---
    details = {}

    # Product Name
    product_match = re.search(r"(?i)([A-Za-z0-9 ]+(?:Chips|Soap|Oil|Biscuits|Snack))", raw_text)
    details['product_name'] = product_match.group(1).strip() if product_match else None

    # Net Weight
    net_match = re.search(r"(?i)NET\s*W[TE]{1,2}[:\s]*([\d\.]+\s?(?:g|kg|ml|l|pcs|packet|pack)?)", raw_text)
    details['net_weight'] = net_match.group(1).strip() if net_match else None

    # MRP
    mrp_match = re.search(r"(?i)MRP\s*[:₹Rs]*\s*([\d\.]+)", raw_text)
    details['mrp'] = mrp_match.group(1).strip() if mrp_match else None

    # Inclusive of all taxes
    details['inclusive_of_all_taxes'] = bool(re.search(r"(?i)inclusive\s*of\s*all\s*taxes", raw_text))

    # Manufacture Date
    mfg_match = re.search(r"(?i)(Mfd|Manufactured\s*on|Mfg)[\s:]*([\d]{1,2}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{4})", raw_text)
    details['mfg_date'] = mfg_match.group(2).strip() if mfg_match else None

    # Country of Origin
    country_match = re.search(r"(?i)Country\s*of\s*Origin[:\s]*([A-Za-z ]+)", raw_text)
    details['country_of_origin'] = country_match.group(1).strip() if country_match else None

    # Manufacturer
    manu_match = re.search(
        r"(?is)(Packed\s*&\s*Marketed\s*by|Manufactured\s*by|Packed\s*by)\s*[:\-]*\s*(.+?)(?:Customer|Phone|Email|$)",
        raw_text
    )
    details['manufacturer'] = manu_match.group(2).strip().replace("\n", " ") if manu_match else None

    # --- Compliance Check ---
    missing_fields = []
    if not details['product_name']: missing_fields.append("Product Name")
    if not details['net_weight']: missing_fields.append("Net Quantity")
    if not details['mrp']: missing_fields.append("MRP")
    if not details['inclusive_of_all_taxes']: missing_fields.append("Inclusive of All Taxes")
    if not details['mfg_date']: missing_fields.append("Manufacture Date")
    if not details['country_of_origin']: missing_fields.append("Country of Origin")
    if not details['manufacturer']: missing_fields.append("Manufacturer Details")

    if missing_fields:
        compliance_status = f"❌ NON-COMPLIANT: Missing {', '.join(missing_fields)}"
    else:
        compliance_status = "✅ COMPLIANT"

    details['compliance_status'] = compliance_status

    # --- Display extracted info ---
    st.subheader("🟢 Extracted Details & Compliance")
    st.json(details)

    # --- Save to CSV ---
    df_existing = pd.read_csv(CSV_FILE)
    df_existing = pd.concat([df_existing, pd.DataFrame([details])], ignore_index=True)
    df_existing.to_csv(CSV_FILE, index=False)

    st.success("✅ Details saved to camera_ocr_products.csv")

    # --- Show stored data ---
    st.subheader("📂 Stored Records")
    st.dataframe(df_existing)
