import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import plotly.express as px

# --- CONFIGURATION ---
st.set_page_config(page_title="My Personal Budget", page_icon="💰", layout="wide")

# --- CONNECT TO GOOGLE SHEETS ---
def get_google_sheet_driver():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("My Personal Budget")

# --- HELPER FUNCTIONS ---
def get_password(sheet_object):
    """Fetches the password from the 'Settings' sheet."""
    try:
        ws = sheet_object.worksheet("Settings")
        # Assuming password is in Cell B2 (Row 2, Col 2)
        return str(ws.cell(2, 2).value)
    except:
        # Fallback if sheet is missing
        return "1234"

def update_password(sheet_object, new_password):
    """Updates the password in the 'Settings' sheet."""
    ws = sheet_object.worksheet("Settings")
    ws.update_cell(2, 2, new_password)

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

    # Force Columns
    if df_exp.empty or 'Date' not in df_exp.columns:
        df_exp = pd.DataFrame(columns=["Date", "Description", "Category", "Amount"])
    if df_inc.empty or 'Date' not in df_inc.columns:
        df_inc = pd.DataFrame(columns=["Date", "Source", "Amount"])

    # Convert Dates
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
st.title("💰 My Personal Budget")

# 1. Connect first to get the real password
try:
    sh = get_google_sheet_driver()
    REAL_PASSWORD = get_password(sh)
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

# 2. Login Check
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if not st.session_state['authenticated']:
    # Show Login Form
    password_input = st.text_input("Enter Password", type="password")
    if st.button("Login"):
        if password_input == REAL_PASSWORD:
            st.session_state['authenticated'] = True
            st.rerun()
        else:
            st.error("Incorrect Password")
    st.stop() # Stop here if not logged in

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    with st.expander("Change Password"):
        with st.form("pwd_change"):
            current_pass = st.text_input("Current Password", type="password")
            new_pass = st.text_input("New Password", type="password")
            confirm_pass = st.text_input("Confirm New Password", type="password")
            
            if st.form_submit_button("Update Password"):
                if current_pass == REAL_PASSWORD:
                    if new_pass == confirm_pass and new_pass != "":
                        update_password(sh, new_pass)
                        st.success("Password Updated! Please login again.")
                        st.session_state['authenticated'] = False # Force logout
                        st.rerun()
                    else:
                        st.error("New passwords do not match.")
                else:
                    st.error("Current password incorrect.")

    st.divider()
    if st.button("Logout"):
        st.session_state['authenticated'] = False
        st.rerun()

# --- MAIN APP (Only runs if authenticated) ---
df_expenses, df_income = load_data(sh)

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
    st.header("Spending Analysis")
    all_dates = pd.concat([df_income['Date'], df_expenses['Date']]).dropna()
    
    if not all_dates.empty:
        # TOGGLE: Monthly vs Annual
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

        # METRICS
        tot_inc = f_inc['Amount'].sum()
        tot_exp = f_exp['Amount'].sum()
        balance = tot_inc - tot_exp
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Income", f"RM {tot_inc:,.2f}")
        c2.metric("Total Expenses", f"RM {tot_exp:,.2f}")
        c3.metric("Balance", f"RM {balance:,.2f}")
        st.divider()

        # CHARTS
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
        # TABLES
        with st.expander("Show Detailed Transaction Records"):
            col_l, col_r = st.columns(2)
            with col_l:
                st.subheader("Expenses List")
                for idx, row in f_exp.iterrows():
                    st.text(f"{row['Date'].date()} | {row['Description']} | RM{row['Amount']}")
                    if st.button("🗑 Delete", key=f"del_e_{idx}"):
                        delete_row(sh, 'Expenses', idx)
                        st.session_state['success_msg'] = "❌ Deleted!"
                        st.rerun()
            with col_r:
                st.subheader("Income List")
                for idx, row in f_inc.iterrows():
                    st.text(f"{row['Date'].date()} | {row['Source']} | RM{row['Amount']}")
                    if st.button("🗑 Delete", key=f"del_i_{idx}"):
                        delete_row(sh, 'Income', idx)
                        st.session_state['success_msg'] = "❌ Deleted!"
                        st.rerun()
    else:
        st.info("No data found.")