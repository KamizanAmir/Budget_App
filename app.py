import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="My Personal Budget", page_icon="💰", layout="wide")

# --- PASSWORD PROTECTION ---
password = st.sidebar.text_input("Enter Password", type="password")
if password != "p@ssw0rd": # Change this to your password
    st.info("🔒 Please enter the password to access the budget.")
    st.stop()

# --- CONNECT TO GOOGLE SHEETS ---
def get_google_sheet_driver():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("My Personal Budget")

# --- HELPER FUNCTIONS ---
def load_data(sheet_object):
    # Load Expenses
    try:
        data_exp = sheet_object.worksheet("Expenses").get_all_records()
        df_exp = pd.DataFrame(data_exp)
    except:
        df_exp = pd.DataFrame()

    # Load Income
    try:
        data_inc = sheet_object.worksheet("Income").get_all_records()
        df_inc = pd.DataFrame(data_inc)
    except:
        df_inc = pd.DataFrame()

    # FORCE COLUMNS & TYPES (The Fix)
    # Even if empty, we enforce the structure
    if df_exp.empty or 'Date' not in df_exp.columns:
        df_exp = pd.DataFrame(columns=["Date", "Description", "Category", "Amount"])
    
    if df_inc.empty or 'Date' not in df_inc.columns:
        df_inc = pd.DataFrame(columns=["Date", "Source", "Amount"])

    # CRITICAL FIX: Always convert to datetime, enforcing errors='coerce' to handle empty strings
    df_exp['Date'] = pd.to_datetime(df_exp['Date'], errors='coerce')
    df_inc['Date'] = pd.to_datetime(df_inc['Date'], errors='coerce')

    return df_exp, df_inc

def save_row(sheet_object, tab_name, data):
    worksheet = sheet_object.worksheet(tab_name)
    worksheet.append_row(data)

def delete_row(sheet_object, tab_name, row_index):
    worksheet = sheet_object.worksheet(tab_name)
    worksheet.delete_rows(row_index + 2)

# --- APP START ---
st.title("💰 My Personal Budget (Cloud Edition)")

try:
    sh = get_google_sheet_driver()
    df_expenses, df_income = load_data(sh)
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

# --- SUCCESS MESSAGE ---
if 'success_msg' in st.session_state:
    st.success(st.session_state['success_msg'])
    del st.session_state['success_msg']

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📥 Add Income", "💸 Add Expense", "📊 Analytics"])

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
            st.rerun()

# --- TAB 2: EXPENSE ---
with tab2:
    st.header("New Expense")
    with st.form("expense_form", clear_on_submit=True):
        d_exp = st.date_input("Date", datetime.date.today())
        c_exp = st.selectbox("Category", ["Food", "Transport", "Utilities", "Shopping", "Housing", "Other"])
        a_exp = st.number_input("Amount", min_value=0.0, format="%.2f")
        desc_exp = st.text_input("Description")
        if st.form_submit_button("Save Expense"):
            save_row(sh, 'Expenses', [str(d_exp), desc_exp, c_exp, a_exp])
            st.session_state['success_msg'] = "✅ Expense Saved!"
            st.rerun()

# --- TAB 3: ANALYTICS ---
with tab3:
    st.header("Overview")
    
    # Combined Date Filter
    # We drop NaT (Not a Time) values to prevent crashes on empty rows
    all_dates = pd.concat([df_income['Date'], df_expenses['Date']]).dropna()
    
    if not all_dates.empty:
        # Now safe to use .dt accessor because we forced conversion in load_data
        month_years = all_dates.dt.to_period('M').drop_duplicates().sort_values(ascending=False)
        selected_period = st.selectbox("Select Month", month_years)
        
        # Filter Logic
        mask_inc = df_income['Date'].dt.to_period('M') == selected_period
        mask_exp = df_expenses['Date'].dt.to_period('M') == selected_period
        
        f_inc = df_income[mask_inc].copy()
        f_exp = df_expenses[mask_exp].copy()
        
        # Metrics
        tot_inc = f_inc['Amount'].sum()
        tot_exp = f_exp['Amount'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Income", f"RM {tot_inc:,.2f}")
        c2.metric("Expenses", f"RM {tot_exp:,.2f}")
        c3.metric("Balance", f"RM {tot_inc - tot_exp:,.2f}")
        
        st.divider()
        
        # Display Tables
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("Expenses")
            for idx, row in f_exp.iterrows():
                st.text(f"{row['Date'].date()} | {row['Description']} | RM{row['Amount']}")
                if st.button("🗑 Delete", key=f"del_e_{idx}"):
                    delete_row(sh, 'Expenses', idx)
                    st.session_state['success_msg'] = "❌ Deleted!"
                    st.rerun()
                    
        with col_r:
            st.subheader("Income")
            for idx, row in f_inc.iterrows():
                st.text(f"{row['Date'].date()} | {row['Source']} | RM{row['Amount']}")
                if st.button("🗑 Delete", key=f"del_i_{idx}"):
                    delete_row(sh, 'Income', idx)
                    st.session_state['success_msg'] = "❌ Deleted!"
                    st.rerun()
    else:
        st.info("No data found. Add your first income or expense to see the dashboard!")
