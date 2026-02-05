import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import plotly.express as px  # NEW: Charting Library

# --- CONFIGURATION ---
st.set_page_config(page_title="My Personal Budget", page_icon="💰", layout="wide")

# --- PASSWORD PROTECTION ---
password = st.sidebar.text_input("Enter Password", type="password")
if password != "p@ssw0rd":
    st.info("🔒 Please enter the password to access the budget.")
    st.stop()

# --- CONNECT TO GOOGLE SHEETS ---
def get_google_sheet_driver():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("My Personal Budget") # Make sure this matches your Sheet Name

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

# --- TAB 3: ANALYTICS (Charts & Graphs) ---
with tab3:
    st.header("Spending Analysis")
    
    # Combined Date Logic
    all_dates = pd.concat([df_income['Date'], df_expenses['Date']]).dropna()
    
    if not all_dates.empty:
        # 1. TOGGLE: Monthly vs Annual
        view_mode = st.radio("Select View Mode:", ["Monthly", "Annual"], horizontal=True)
        
        f_inc = df_income.copy()
        f_exp = df_expenses.copy()
        
        # 2. FILTER DATA based on Toggle
        if view_mode == "Monthly":
            # Get list of Month-Years
            month_years = all_dates.dt.to_period('M').drop_duplicates().sort_values(ascending=False)
            selected_period = st.selectbox("Select Month", month_years)
            
            # Filter
            mask_inc = f_inc['Date'].dt.to_period('M') == selected_period
            mask_exp = f_exp['Date'].dt.to_period('M') == selected_period
            f_inc = f_inc[mask_inc]
            f_exp = f_exp[mask_exp]
        else:
            # Annual: Filter by Year
            years = all_dates.dt.year.unique()
            selected_year = st.selectbox("Select Year", sorted(years, reverse=True))
            
            mask_inc = f_inc['Date'].dt.year == selected_year
            mask_exp = f_exp['Date'].dt.year == selected_year
            f_inc = f_inc[mask_inc]
            f_exp = f_exp[mask_exp]

        # 3. METRICS (Top Row)
        tot_inc = f_inc['Amount'].sum()
        tot_exp = f_exp['Amount'].sum()
        balance = tot_inc - tot_exp
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Income", f"RM {tot_inc:,.2f}")
        c2.metric("Total Expenses", f"RM {tot_exp:,.2f}")
        c3.metric("Balance", f"RM {balance:,.2f}", delta_color="normal")
        
        st.divider()

        # 4. CHARTS (The new UI/UX part!)
        if not f_exp.empty:
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.subheader("Spending by Category")
                # Group data for Pie Chart
                pie_data = f_exp.groupby("Category")["Amount"].sum().reset_index()
                fig_pie = px.pie(pie_data, values='Amount', names='Category', hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col_chart2:
                st.subheader("Income vs Expenses")
                # Simple Bar Chart Comparison
                bar_data = pd.DataFrame({
                    "Type": ["Income", "Expenses"],
                    "Amount": [tot_inc, tot_exp]
                })
                fig_bar = px.bar(bar_data, x="Type", y="Amount", color="Type", 
                                 color_discrete_map={"Income": "green", "Expenses": "red"})
                st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No expenses found for this period, so no charts to show.")

        st.divider()
        
        # 5. DATA TABLES (View & Delete)
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
        st.info("No data found. Add your first income or expense!")