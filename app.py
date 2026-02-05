import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="My Personal Budget", page_icon="💰", layout="wide")

# --- PASSWORD PROTECTION ---
# Create a password input in the sidebar
password = st.sidebar.text_input("Enter Password", type="password")

# Replace "1234" with whatever secret code you want
if password != "p@ssw0rd":
    st.info("🔒 Please enter the password to access the budget.")
    st.stop() # This stops the rest of the app from loading

# --- CONNECT TO GOOGLE SHEETS ---
def get_google_sheet_driver():
    """Connects to Google Sheets using Streamlit Secrets."""
    # We load the secrets from the TOML configuration we set up in Streamlit Cloud
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"]) # Convert TOML object to dict
    
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    # Open the sheet by Name (Make sure your Google Sheet is named EXACTLY this)
    # Or you can use .open_by_key('YOUR_SHEET_ID_FROM_URL') which is safer
    sheet = client.open("My Personal Budget") 
    return sheet

# --- HELPER FUNCTIONS ---
def load_data(sheet_object):
    """Loads data from Google Sheets into Pandas DataFrames."""
    # Get all values from Expenses tab
    worksheet_exp = sheet_object.worksheet("Expenses")
    data_exp = worksheet_exp.get_all_records()
    df_exp = pd.DataFrame(data_exp)

    # Get all values from Income tab
    worksheet_inc = sheet_object.worksheet("Income")
    data_inc = worksheet_inc.get_all_records()
    df_inc = pd.DataFrame(data_inc)
    
    return df_exp, df_inc

def save_row(sheet_object, tab_name, data):
    """Appends a row to the specific Google Sheet tab."""
    worksheet = sheet_object.worksheet(tab_name)
    worksheet.append_row(data)

def delete_row(sheet_object, tab_name, row_index):
    """Deletes a row. Note: row_index is 0-based from DataFrame."""
    worksheet = sheet_object.worksheet(tab_name)
    # Google Sheets is 1-based. Header is Row 1. Data starts Row 2.
    # If DataFrame index is 0, that is Sheet Row 2.
    worksheet.delete_rows(row_index + 2)

# --- APP START ---
st.title("💰 My Personal Budget (Cloud Edition)")

try:
    sh = get_google_sheet_driver()
    df_expenses, df_income = load_data(sh)
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

# --- SUCCESS MESSAGE HANDLING ---
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
            # Convert date to string for Google Sheets
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
    
    # Basic Data Cleanup for display
    if not df_income.empty:
        df_income['Date'] = pd.to_datetime(df_income['Date'])
    if not df_expenses.empty:
        df_expenses['Date'] = pd.to_datetime(df_expenses['Date'])
        
    # --- Month Filter (Same logic as before) ---
    all_dates = pd.concat([df_income['Date'], df_expenses['Date']]).dropna()
    
    if not all_dates.empty:
        month_years = all_dates.dt.to_period('M').drop_duplicates().sort_values(ascending=False)
        selected_period = st.selectbox("Select Month", month_years)
        
        mask_inc = df_income['Date'].dt.to_period('M') == selected_period
        mask_exp = df_expenses['Date'].dt.to_period('M') == selected_period
        
        f_inc = df_income[mask_inc].copy()
        f_exp = df_expenses[mask_exp].copy()
        
        # Metrics
        tot_inc = f_inc['Amount'].sum() if not f_inc.empty else 0
        tot_exp = f_exp['Amount'].sum() if not f_exp.empty else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Income", f"RM {tot_inc:,.2f}")
        c2.metric("Expenses", f"RM {tot_exp:,.2f}")
        c3.metric("Balance", f"RM {tot_inc - tot_exp:,.2f}")
        
        st.divider()
        
        # Display & Delete
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("Expenses")
            for idx, row in f_exp.iterrows():
                # Display row
                st.text(f"{row['Date'].date()} | {row['Description']} | RM{row['Amount']}")
                # Delete Button
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
        st.info("No data found in Google Sheet.")
