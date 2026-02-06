import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import plotly.express as px
import io
import numpy as np
import re

# --- AI LIBRARY SETUP ---
try:
    import easyocr
    import cv2
    # Initialize reader once (cpu mode for free cloud)
    ocr_reader = easyocr.Reader(['en'], gpu=False) 
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# --- CONFIGURATION ---
st.set_page_config(page_title="Budget Tracker", page_icon="💰", layout="wide")

# --- CONNECT TO GOOGLE SHEETS (API) ---
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- USER MANAGEMENT ---
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
        st.error(f"Login Error: {e}")
    return None

def register_user_request(username, password, preferred_sheet_name):
    client = get_client()
    try:
        master_sheet = client.open("Budget_App_Users").sheet1
        master_sheet.append_row([username, password, preferred_sheet_name]) 
        return True, f"Request sent! Wait for Admin to create '{preferred_sheet_name}'."
    except Exception as e:
        return False, f"Database Error: {e}"

# --- AI SCANNER ---
def scan_receipt_for_total(uploaded_file):
    if not OCR_AVAILABLE or uploaded_file is None: return 0.00
    try:
        file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_GRAYSCALE)
        result_text = ocr_reader.readtext(img, detail=0)
        full_text = " ".join(result_text)
        # Regex to find numbers that look like prices
        matches = re.findall(r"(\d{1,3}(?:,\d{3})*(?:\.\d{2}))", full_text)
        max_price = 0.0
        for match in matches:
            clean_price = float(match.replace(',', ''))
            if clean_price > max_price: max_price = clean_price
        return max_price
    except Exception as e:
        st.error(f"AI Error: {e}")
        return 0.00

# --- SESSION STATE ---
if 'user_sheet_name' not in st.session_state: st.session_state['user_sheet_name'] = None
if 'username' not in st.session_state: st.session_state['username'] = None
if 'current_view' not in st.session_state: st.session_state['current_view'] = "📥 Add Income"

# ==========================================
#  SCENE 1: LOGIN
# ==========================================
if st.session_state['user_sheet_name'] is None:
    st.title("🔐 Budget Tracker")
    tab_login, tab_signup = st.tabs(["Login", "Request Account"])
    
    with tab_login:
        with st.form("login_form"):
            user = st.text_input("Username")
            pwd = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                sheet = check_login(user, pwd)
                if sheet:
                    st.session_state['user_sheet_name'] = sheet
                    st.session_state['username'] = user
                    st.rerun()
                else:
                    st.error("Invalid Credentials")

    with tab_signup:
        with st.form("signup_form"):
            nu = st.text_input("Choose Username")
            npwd = st.text_input("Choose Password", type="password")
            nsheet = st.text_input("Preferred Sheet Name")
            if st.form_submit_button("Submit Request"):
                if nu and npwd and nsheet:
                    s, m = register_user_request(nu, npwd, nsheet)
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
        st.warning("Account Pending Activation.")
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
            st.rerun()

    # --- HELPERS ---
    def load_data(sheet_obj):
        try: df_e = pd.DataFrame(sheet_obj.worksheet("Expenses").get_all_records())
        except: df_e = pd.DataFrame()
        try: df_i = pd.DataFrame(sheet_obj.worksheet("Income").get_all_records())
        except: df_i = pd.DataFrame()
        
        if df_e.empty or 'Date' not in df_e.columns: df_e = pd.DataFrame(columns=["Date", "Description", "Category", "Amount"])
        if df_i.empty or 'Date' not in df_i.columns: df_i = pd.DataFrame(columns=["Date", "Source", "Amount"])
        
        df_e['Date'] = pd.to_datetime(df_e['Date'], errors='coerce')
        df_i['Date'] = pd.to_datetime(df_i['Date'], errors='coerce')
        return df_e, df_i

    def save_row(sheet_obj, tab_name, data):
        try: ws = sheet_obj.worksheet(tab_name)
        except:
            ws = sheet_obj.add_worksheet(title=tab_name, rows="1000", cols="10")
            head = ["Date", "Description", "Category", "Amount"] if tab_name == "Expenses" else ["Date", "Source", "Amount"]
            ws.append_row(head)
        ws.append_row(data)

    def delete_row(sheet_obj, tab_name, idx):
        sheet_obj.worksheet(tab_name).delete_rows(idx + 2)

    df_exp, df_inc = load_data(sh)
    if 'success_msg' in st.session_state:
        st.success(st.session_state['success_msg'])
        del st.session_state['success_msg']

    st.title(f"💰 {st.session_state['username'].capitalize()}'s Budget")

    # --- NAVIGATION ---
    nav_options = ["📥 Add Income", "💸 Add Expense", "📊 Analytics"]
    selection = st.radio("", nav_options, horizontal=True, key="current_view")
    
    st.divider()

    # --- VIEW 1: INCOME ---
    if selection == "📥 Add Income":
        st.header("New Income")
        with st.form("income_form", clear_on_submit=True):
            d = st.date_input("Date", datetime.date.today())
            s = st.text_input("Source")
            a = st.number_input("Amount", min_value=0.0, format="%.2f")
            if st.form_submit_button("Save Income"):
                save_row(sh, 'Income', [str(d), s, a])
                st.session_state['success_msg'] = "✅ Income Saved!"
                st.rerun()

    # --- VIEW 2: EXPENSE ---
    elif selection == "💸 Add Expense":
        st.header("New Expense")
        
        if not OCR_AVAILABLE:
            st.caption("⚠️ AI Scanner unavailable (libraries missing). Manual entry only.")
        else:
            st.caption("🤖 Optional: Upload receipt to auto-detect total.")
            uploaded_file = st.file_uploader("Upload Receipt", type=['png', 'jpg', 'jpeg'])
            if uploaded_file:
                # Check if new file to avoid re-scanning on every interaction
                if 'last_file' not in st.session_state or st.session_state['last_file'] != uploaded_file.name:
                    with st.spinner("Scanning..."):
                        val = scan_receipt_for_total(uploaded_file)
                        if val > 0:
                            # Update the Widget State directly
                            st.session_state['expense_amount_input'] = val 
                            st.toast(f"Detected: RM{val}", icon="🤖")
                        else:
                            st.toast("No clear price found.", icon="⚠️")
                    st.session_state['last_file'] = uploaded_file.name

        with st.form("expense_form", clear_on_submit=True):
            d = st.date_input("Date", datetime.date.today())
            c = st.selectbox("Category", ["Food", "Transport", "Utilities", "Shopping", "Housing", "Other"])
            desc = st.text_input("Description")
            
            # BUG FIX: Removed 'value=' argument. 
            # We use 'key' to let Streamlit manage the state, and we manually update that key ONLY when AI runs.
            a = st.number_input("Amount", min_value=0.0, format="%.2f", key="expense_amount_input")
            
            if st.form_submit_button("Save Expense"):
                save_row(sh, 'Expenses', [str(d), desc, c, a])
                st.session_state['success_msg'] = "✅ Expense Saved!"
                
                # Clear the amount for the next entry
                st.session_state['expense_amount_input'] = 0.00
                if 'last_file' in st.session_state: del st.session_state['last_file']
                st.rerun()

    # --- VIEW 3: ANALYTICS ---
    elif selection == "📊 Analytics":
        st.header("Spending Analysis")
        all_dates = pd.concat([df_inc['Date'], df_exp['Date']]).dropna()
        
        if not all_dates.empty:
            view_mode = st.radio("View Mode:", ["Monthly", "Annual"], horizontal=True)
            f_i, f_e = df_inc.copy(), df_exp.copy()
            
            if view_mode == "Monthly":
                periods = all_dates.dt.to_period('M').drop_duplicates().sort_values(ascending=False)
                sel_p = st.selectbox("Select Month", periods)
                f_i = f_i[f_i['Date'].dt.to_period('M') == sel_p]
                f_e = f_e[f_e['Date'].dt.to_period('M') == sel_p]
            else:
                years = sorted(all_dates.dt.year.unique(), reverse=True)
                sel_y = st.selectbox("Select Year", years)
                f_i = f_i[f_i['Date'].dt.year == sel_y]
                f_e = f_e[f_e['Date'].dt.year == sel_y]
            
            # Sort
            f_i = f_i.sort_values("Date", ascending=False)
            f_e = f_e.sort_values("Date", ascending=False)

            # Metrics
            ti, te = f_i['Amount'].sum(), f_e['Amount'].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Income", f"RM {ti:,.2f}")
            c2.metric("Expenses", f"RM {te:,.2f}")
            c3.metric("Balance", f"RM {ti - te:,.2f}")
            
            st.divider()

            # Charts
            if not f_e.empty:
                cl, cr = st.columns(2)
                with cl:
                    st.subheader("Category Split")
                    pie = f_e.groupby("Category")["Amount"].sum().reset_index()
                    st.plotly_chart(px.pie(pie, values='Amount', names='Category', hole=0.4), use_container_width=True)
                with cr:
                    st.subheader("In vs Out")
                    bar = pd.DataFrame({"Type": ["Income", "Expenses"], "Amount": [ti, te]})
                    st.plotly_chart(px.bar(bar, x="Type", y="Amount", color="Type"), use_container_width=True)
            else:
                st.info("No data for charts.")
            
            st.divider()

            # Detailed Records & Export
            with st.expander("Detailed Records", expanded=True):
                # Excel Export
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    f_e.to_excel(writer, sheet_name='Expenses', index=False)
                    f_i.to_excel(writer, sheet_name='Income', index=False)
                
                st.download_button("📥 Download Report (Excel)", data=buffer.getvalue(), 
                                   file_name=f"Report_{view_mode}.xlsx", 
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                
                st.markdown("---")
                l, r = st.columns(2)
                with l:
                    st.subheader("Expenses")
                    col1, col2, col3, col4 = st.columns([2,3,2,1])
                    col1.markdown("**Date**"); col2.markdown("**Desc**"); col3.markdown("**Amt**");
                    for idx, row in f_e.iterrows():
                        c1, c2, c3, c4 = st.columns([2,3,2,1])
                        c1.write(row['Date'].strftime('%Y-%m-%d'))
                        c2.write(f"{row['Category']} - {row['Description']}")
                        c3.write(f"RM{row['Amount']}")
                        if c4.button("🗑", key=f"de{idx}"):
                            delete_row(sh, 'Expenses', idx)
                            st.session_state['success_msg'] = "Deleted!"
                            # Removed line that caused crash: st.session_state['current_view'] = ...
                            st.rerun()
                with r:
                    st.subheader("Income")
                    col1, col2, col3, col4 = st.columns([2,3,2,1])
                    col1.markdown("**Date**"); col2.markdown("**Src**"); col3.markdown("**Amt**");
                    for idx, row in f_i.iterrows():
                        c1, c2, c3, c4 = st.columns([2,3,2,1])
                        c1.write(row['Date'].strftime('%Y-%m-%d'))
                        c2.write(row['Source'])
                        c3.write(f"RM{row['Amount']}")
                        if c4.button("🗑", key=f"di{idx}"):
                            delete_row(sh, 'Income', idx)
                            st.session_state['success_msg'] = "Deleted!"
                            # Removed line that caused crash: st.session_state['current_view'] = ...
                            st.rerun()
        else:
            st.info("No data found.")