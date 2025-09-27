import streamlit as st
import sys
import subprocess
import os
import platform

st.title("🔍 Debug Information")

# Show Python version and platform
st.subheader("System Information")
st.write(f"Python version: {sys.version}")
st.write(f"Platform: {platform.platform()}")
st.write(f"Architecture: {platform.architecture()}")

# Check installed packages
st.subheader("Installed Packages")
try:
    result = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True)
    if "pytesseract" in result.stdout:
        st.success("✅ pytesseract is installed")
    else:
        st.error("❌ pytesseract is NOT installed")
    
    st.text("Installed packages:")
    st.text(result.stdout)
except Exception as e:
    st.error(f"Error checking packages: {e}")

# Check tesseract binary
st.subheader("Tesseract Binary Check")
try:
    if platform.system() != "Windows":
        result = subprocess.run(['which', 'tesseract'], capture_output=True, text=True)
        if result.returncode == 0:
            st.success(f"✅ Tesseract binary found at: {result.stdout.strip()}")
            
            # Check tesseract version
            version_result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True)
            st.text(f"Tesseract version: {version_result.stdout}")
        else:
            st.error("❌ Tesseract binary not found")
    else:
        st.info("Running on Windows - skipping binary check")
except Exception as e:
    st.error(f"Error checking tesseract: {e}")

# Try importing pytesseract
st.subheader("Import Test")
try:
    import pytesseract
    st.success("✅ Successfully imported pytesseract")
    
    # Try basic functionality
    try:
        version = pytesseract.get_tesseract_version()
        st.success(f"✅ Pytesseract version: {version}")
    except Exception as e:
        st.error(f"❌ Error getting tesseract version: {e}")
        
except ImportError as e:
    st.error(f"❌ Failed to import pytesseract: {e}")
    
    # Try to install it
    st.info("Attempting to install pytesseract...")
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "install", "pytesseract"], 
                              capture_output=True, text=True)
        st.text(f"Install output: {result.stdout}")
        if result.stderr:
            st.text(f"Install errors: {result.stderr}")
    except Exception as install_e:
        st.error(f"Installation failed: {install_e}")