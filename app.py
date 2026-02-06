import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import plotly.express as px
import io
import numpy as np
import re
# Import OCR library (wrap in try block to prevent crashing if install fails)
try:
    import easyocr
    import cv2
    # Initialize reader once (it takes memory)
    # Using CPU ('gpu=False') for free cloud compatibility
    ocr_reader = easyocr.Reader(['en'], gpu=False) 
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    st.warning("AI libraries (easyocr/cv2) not installed. Receipt scanning disabled.")

# --- CONFIGURATION ---
st.set_page_config(page_title="Budget Tracker", page_icon="💰", layout="wide")

# --- CONNECT TO GOOGLE SHEETS (API) ---
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- USER MANAGEMENT FUNCTIONS ---
def check_login(username, password):
    client = get_client()
    try:
        user_sheet = client.open("Budget_App_Users").sheet1
        records = user_sheet.get_all_records()
        df_users = pd.DataFrame(records)
        user_row = df_users[df_users['Username'].astype(str) == str(username)]
        if not user_row.empty:
            stored_password = str(user_row.iloc[0]['Password'])
            if str(password) == stored_password:
                return str(user_row.iloc[0]['Sheet_Name'])
    except Exception as e:
        st.error(f"Login System Error: {e}")
    return None

def register_user_request(username, password, preferred_sheet_name):
    client = get_client()
    try:
        master_sheet = client.open("Budget_App_Users").sheet1
        master_sheet.append_row([username, password, preferred_sheet_name]) 
        return True, f"Request sent! Wait for Admin to create '{preferred_sheet_name}'."
    except Exception as e:
        return False, f"Database Error: {e}"

# --- AI HELPER FUNCTION ---
def scan_receipt_for_total(uploaded_file):
    """Uses EasyOCR to find the largest detected price in an image."""
    if not OCR_AVAILABLE or uploaded_file is None:
        return 0.00

    try:
        # Convert uploaded file to an image format OpenCV understands
        file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_GRAYSCALE)

        # Run OCR
        result_text = ocr_reader.readtext(img, detail=0)
        full_text = " ".join(result_text)

        # Regex to find price-like patterns (e.g., 12.99, 1,200.50)
        # This is a basic regex and might need tuning based on your receipts
        price_pattern = r"(\d{1,3}(?:,\d{3})*(?:\.\d{2}))"
        matches = re.findall(price_pattern, full_text)

        max_price = 0.0
        for match in matches:
            # Remove commas to convert to float
            clean_price = float(match.replace(',', ''))
            if clean_price > max_price:
                max_price = clean_price
        
        return max_price
    except Exception as e:
        st.error(f"AI Scan Error: {e}")
        return 0.00

# --- SESSION STATE INITIALIZATION ---
if 'user_sheet_name' not in st.session_state: st.session_state['user_sheet_name'] = None
if 'username' not in st.session_state: st.session_state['username'] = None
# FIX: Add state to remember which tab was open
if 'active_tab_idx' not in st.session_state: st.session_state['active_tab_idx'] = 0 # Default to first tab
# FIX: State for scanned amount
if 'scanned_amount' not in st.session_state: st.session_state['scanned_amount'] = 0.00

# ==========================================
#  SCENE 1: LOGIN / REQUEST
# ==========================================
if st.session_state['user_sheet_name'] is None:
    st.title("🔐 Budget Tracker")
    tab_login, tab_signup = st.tabs(["Login", "Request Account"])
    
    with tab_login:
        with st.form("login_form"):
            user_input = st.text_input("Username")
            pass_input = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                sheet_name = check_login(user_input, pass_input)
                if sheet_name:
                    st.session_state['user_sheet_name'] = sheet_name
                    st.session_state['username'] = user_input
                    st.rerun()
                else:
                    st.error("Invalid Credentials")

    with tab_signup:
        with st.form("signup_form"):
            new_user = st.text_input("Choose Username")
            new_pass = st.text_input("Choose Password", type="password")
            pref_sheet = st.text_input("Preferred Sheet Name")
            if st.form_submit_button("Submit Request"):
                if new_user and new_pass and pref_sheet:
                    s, m = register_user_request(new_user, new_pass, pref_sheet)
                    if s: st.success(m)
                    else: st.error(m)
                else: st.warning("Fill all fields.")

else:
    # ==========================================
    #  SCENE 2: MAIN APP
    # ==========================================
    try:
        client = get_client()
        sh = client.open(st.session_state['user_sheet_name']) 
    except gspread.exceptions.SpreadsheetNotFound:
        st.warning(f"Account Pending. Admin has not created sheet '{st.session_state['user_sheet_name']}' yet.")
        if st.button("Logout"):
            st.session_state['user_sheet_name'] = None
            st.rerun()
        st.stop()
    except Exception as e:
        st.error(f"Connection Error: {e}")
        st.stop()

    with st.sidebar:
        st.write(f"User: **{st.session_state['username']}**")
        if st.button("Logout"):
            st.session_state['user_sheet_name'] = None
            st.session_state['active_tab_idx'] = 0
            st.rerun()

    # --- HELPER FUNCTIONS ---
    def load_data(sheet_object):
        try: df_exp = pd.DataFrame(sheet_object.worksheet("Expenses").get_all_records())
        except: df_exp = pd.DataFrame()
        try: df_inc = pd.DataFrame(sheet_object.worksheet("Income").get_all_records())
        except: df_inc = pd.DataFrame()
        if df_exp.empty or 'Date' not in df_exp.columns: df_exp = pd.DataFrame(columns=["Date", "Description", "Category", "Amount"])
        if df_inc.empty or 'Date' not in df_inc.columns: df_inc = pd.DataFrame(columns=["Date", "Source", "Amount"])
        df_exp['Date'] = pd.to_datetime(df_exp['Date'], errors='coerce')
        df_inc['Date'] = pd.to_datetime(df_inc['Date'], errors='coerce')
        return df_exp, df_inc

    def save_row(sheet_object, tab_name, data):
        try: worksheet = sheet_object.worksheet(tab_name)
        except:
            worksheet = sheet_object.add_worksheet(title=tab_name, rows="1000", cols="10")
            header = ["Date", "Description", "Category", "Amount"] if tab_name == "Expenses" else ["Date", "Source", "Amount"]
            worksheet.append_row(header)
        worksheet.append_row(data)

    def delete_row(sheet_object, tab_name, row_index):
        sheet_object.worksheet(tab_name).delete_rows(row_index + 2)

    # --- LOAD DATA & MESSAGES ---
    df_expenses, df_income = load_data(sh)
    if 'success_msg' in st.session_state:
        st.success(st.session_state['success_msg'])
        del st.session_state['success_msg']

    st.title(f"💰 {st.session_state['username'].capitalize()}'s Budget")

    # FIX: Use session state to remember the active tab index
    tab1, tab2, tab3 = st.tabs(["📥 Add Income", "💸 Add Expense", "📊 Analytics"], index=st.session_state['active_tab_idx'])

    # --- TAB 1: INCOME ---
    with tab1:
        st.header("New Income")
        with st.form("income_form", clear_on_submit=True):
            d_inc = st.date_input("Date", datetime.date.today())
            s_inc = st.text_input("Source")
            a_inc = st.number_input("Amount", min_value=0.0, format="%.2f")
            if st.form_submit_button("Save Income"):
                save_row(sh, 'Income', [str(d_inc), s_inc, a_inc])
                st.session_state['success_msg'] = "✅ Income Saved!"
                # FIX: Remember we are on tab index 0
                st.session_state['active_tab_idx'] = 0
                st.rerun()

    # --- TAB 2: EXPENSE (With AI) ---
    with tab2:
        st.header("New Expense")
        
        # AI Section outside the form
        st.caption("🤖 Optional: Upload receipt to auto-detect total amount.")
        uploaded_receipt = st.file_uploader("Upload Receipt (Image)", type=['png', 'jpg', 'jpeg'])
        
        # Logic: If a file is uploaded and we haven't scanned it yet, run AI
        if uploaded_receipt is not None:
             # Simple check to ensure we don't re-scan the same file repeatedly on rerun
            if 'last_scanned_file' not in st.session_state or st.session_state['last_scanned_file'] != uploaded_receipt.name:
                with st.spinner("🤖 AI is reading receipt... (this might take a moment)"):
                    detected_amount = scan_receipt_for_total(uploaded_receipt)
                    if detected_amount > 0:
                        st.session_state['scanned_amount'] = detected_amount
                        st.toast(f"AI detected amount: RM{detected_amount:.2f}", icon="🤖")
                    else:
                         st.toast("AI could not detect a clear total amount.", icon="⚠️")
                    # Mark this file as scanned
                    st.session_state['last_scanned_file'] = uploaded_receipt.name

        with st.form("expense_form", clear_on_submit=True):
            d_exp = st.date_input("Date", datetime.date.today())
            c_exp = st.selectbox("Category", ["Food", "Transport", "Utilities", "Shopping", "Housing", "Other"])
            desc_exp = st.text_input("Description")
            
            # Use the session state amount if available, otherwise default to 0.00
            initial_amount = st.session_state.get('scanned_amount', 0.00)
            a_exp = st.number_input("Amount", min_value=0.0, format="%.2f", value=initial_amount)
            st.caption("Verify the amount before saving.")

            if st.form_submit_button("Save Expense"):
                save_row(sh, 'Expenses', [str(d_exp), desc_exp, c_exp, a_exp])
                st.session_state['success_msg'] = "✅ Expense Saved!"
                # FIX: Remember we are on tab index 1
                st.session_state['active_tab_idx'] = 1
                # Reset scanned amount for next entry
                st.session_state['scanned_amount'] = 0.00
                if 'last_scanned_file' in st.session_state: del st.session_state['last_scanned_file']
                st.rerun()

    # --- TAB 3: ANALYTICS ---
    with tab3:
        # (Analytics code remains exactly the same as before, just indented under this block)
        st.header("Spending Analysis")
        all_dates = pd.concat([df_income['Date'], df_expenses['Date']]).dropna()
        
        if not all_dates.empty:
            view_mode = st.radio("Select View Mode:", ["Monthly", "Annual"], horizontal=True)
            f_inc, f_exp = df_income.copy(), df_expenses.copy()
            
            if view_mode == "Monthly":
                month_years = all_dates.dt.to_period('M').drop_duplicates().sort_values(ascending=False)
                selected_period = st.selectbox("Select Month", month_years)
                mask_inc = f_inc['Date'].dt.to_period('M') == selected_period
                mask_exp = f_exp['Date'].dt.to_period('M') == selected_period
                f_inc, f_exp = f_inc[mask_inc], f_exp[mask_exp]
            else:
                years = all_dates.dt.year.unique()
                selected_year = st.selectbox("Select Year", sorted(years, reverse=True))
                mask_inc = f_inc['Date'].dt.year == selected_year
                mask_exp = f_exp['Date'].dt.year == selected_year
                f_inc, f_exp = f_inc[mask_inc], f_exp[mask_exp]
            
            f_inc = f_inc.sort_values(by="Date", ascending=False)
            f_exp = f_exp.sort_values(by="Date", ascending=False)

            tot_inc = f_inc['Amount'].sum()
            tot_exp = f_exp['Amount'].sum()
            balance = tot_inc - tot_exp
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Income", f"RM {tot_inc:,.2f}")
            c2.metric("Total Expenses", f"RM {tot_exp:,.2f}")
            c3.metric("Balance", f"RM {balance:,.2f}")
            st.divider()

            if not f_exp.empty:
                col_chart1, col_chart2 = st.columns(2)
                with col_chart1:
                    st.subheader("Spending by Category")
                    pie_data = f_exp.groupby("Category")["Amount"].sum().reset_index()
                    fig_pie = px.pie(pie_data, values='Amount', names='Category', hole=0.4)
                    st.plotly_chart(fig_pie, use_container_width=True)
                with col_chart2:
                    st.subheader("Income vs Expenses")
                    bar_data = pd.DataFrame({"Type": ["Income", "Expenses"], "Amount": [tot_inc, tot_exp]})
                    fig_bar = px.bar(bar_data, x="Type", y="Amount", color="Type", color_discrete_map={"Income": "green", "Expenses": "red"})
                    st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("No expenses found for this period.")
            
            st.divider()

            with st.expander("Show Detailed Transaction Records", expanded=True):
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    f_exp.to_excel(writer, sheet_name='Expenses', index=False)
                    f_inc.to_excel(writer, sheet_name='Income', index=False)
                    
                st.download_button(
                    label="📥 Download Report (Excel)",
                    data=buffer.getvalue(),
                    file_name=f"Budget_Report_{view_mode}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.markdown("---")
                list_col_l, list_col_r = st.columns(2)
                with list_col_l:
                    st.subheader("Expenses List")
                    h1, h2, h3, h4 = st.columns([2, 3, 2, 1])
                    h1.markdown("**Date**")
                    h2.markdown("**Description**")
                    h3.markdown("**Amount**")
                    h4.markdown("**Del**")
                    for idx, row in f_exp.iterrows():
                        r1, r2, r3, r4 = st.columns([2, 3, 2, 1])
                        r1.write(row['Date'].strftime('%Y-%m-%d'))
                        r2.write(f"{row['Category']} - {row['Description']}")
                        r3.write(f"RM{row['Amount']}")
                        if r4.button("🗑", key=f"del_e_{idx}"):
                            delete_row(sh, 'Expenses', idx)
                            st.session_state['success_msg'] = "❌ Deleted!"
                            # FIX: Remember we are on tab index 2 (Analytics)
                            st.session_state['active_tab_idx'] = 2
                            st.rerun()

                with list_col_r:
                    st.subheader("Income List")
                    h1, h2, h3, h4 = st.columns([2, 3, 2, 1])
                    h1.markdown("**Date**")
                    h2.markdown("**Source**")
                    h3.markdown("**Amount**")
                    h4.markdown("**Del**")
                    for idx, row in f_inc.iterrows():
                        r1, r2, r3, r4 = st.columns([2, 3, 2, 1])
                        r1.write(row['Date'].strftime('%Y-%m-%d'))
                        r2.write(row['Source'])
                        r3.write(f"RM{row['Amount']}")
                        if r4.button("🗑", key=f"del_i_{idx}"):
                            delete_row(sh, 'Income', idx)
                            st.session_state['success_msg'] = "❌ Deleted!"
                            # FIX: Remember we are on tab index 2
                            st.session_state['active_tab_idx'] = 2
                            st.rerun()
        else:
            st.info("No data found.")