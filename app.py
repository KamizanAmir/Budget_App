import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import plotly.express as px

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
        records = master_sheet.get_all_records()
        df_users = pd.DataFrame(records)
        if not df_users.empty and str(username) in df_users['Username'].astype(str).values:
            return False, "Username already taken."
    except:
        pass 

    try:
        master_sheet.append_row([username, password, preferred_sheet_name]) 
        return True, f"Request sent! Please wait for the Admin to create the sheet '{preferred_sheet_name}'."
    except Exception as e:
        return False, f"Database Error: {e}"

def change_user_password(username, new_password):
    client = get_client()
    user_sheet = client.open("Budget_App_Users").sheet1
    try:
        cell = user_sheet.find(username)
        user_sheet.update_cell(cell.row, 2, new_password)
        return True
    except:
        return False

# --- SESSION STATE ---
if 'user_sheet_name' not in st.session_state:
    st.session_state['user_sheet_name'] = None
if 'username' not in st.session_state:
    st.session_state['username'] = None

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
            submit_login = st.form_submit_button("Login")
            
            if submit_login:
                sheet_name = check_login(user_input, pass_input)
                
                if sheet_name:
                    st.session_state['user_sheet_name'] = sheet_name
                    st.session_state['username'] = user_input
                    st.rerun()
                else:
                    st.error("Invalid Username or Password")

    with tab_signup:
        st.info("ℹ️ Enter the name of the sheet you want the Admin to create for you.")
        with st.form("signup_form"):
            new_user = st.text_input("Choose Username")
            new_pass = st.text_input("Choose Password", type="password")
            pref_sheet = st.text_input("Preferred Sheet Name (e.g. My Budget 2026)")
            
            submit_signup = st.form_submit_button("Submit Request")
            
            if submit_signup:
                if new_user and new_pass and pref_sheet:
                    success, message = register_user_request(new_user, new_pass, pref_sheet)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                else:
                    st.warning("Please fill in all fields.")

else:
    # ==========================================
    #  SCENE 2: MAIN APP
    # ==========================================
    try:
        client = get_client()
        sh = client.open(st.session_state['user_sheet_name']) 
    except gspread.exceptions.SpreadsheetNotFound:
        st.warning(f"⏳ **Account Pending Activation**")
        st.info(f"The Admin has not created your sheet **'{st.session_state['user_sheet_name']}'** yet.")
        if st.button("Back to Login"):
            st.session_state['user_sheet_name'] = None
            st.rerun()
        st.stop()
    except Exception as e:
        st.error(f"Connection Error: {e}")
        st.stop()

    # --- SIDEBAR ---
    with st.sidebar:
        st.write(f"User: **{st.session_state['username']}**")
        
        with st.expander("⚙️ Change Password"):
            with st.form("pwd_change_form"):
                curr_pass = st.text_input("Current Password", type="password")
                new_pass = st.text_input("New Password", type="password")
                conf_pass = st.text_input("Confirm Password", type="password")
                
                if st.form_submit_button("Update"):
                    real_sheet_check = check_login(st.session_state['username'], curr_pass)
                    if real_sheet_check:
                        if new_pass == conf_pass and new_pass != "":
                            if change_user_password(st.session_state['username'], new_pass):
                                st.success("Updated! Logging out...")
                                st.session_state['user_sheet_name'] = None
                                st.rerun()
                            else:
                                st.error("Database Error.")
                        else:
                            st.error("Passwords do not match.")
                    else:
                        st.error("Current password incorrect.")
        
        st.divider()
        if st.button("Logout"):
            st.session_state['user_sheet_name'] = None
            st.rerun()

    # --- HELPER FUNCTIONS ---
    def load_data(sheet_object):
        try:
            data_exp = sheet_object.worksheet("Expenses").get_all_records()
            df_exp = pd.DataFrame(data_exp)
        except:
            df_exp = pd.DataFrame()
        try:
            data_inc = sheet_object.worksheet("Income").get_all_records()
            df_inc = pd.DataFrame(data_inc)
        except:
            df_inc = pd.DataFrame()

        if df_exp.empty or 'Date' not in df_exp.columns:
            df_exp = pd.DataFrame(columns=["Date", "Description", "Category", "Amount"])
        if df_inc.empty or 'Date' not in df_inc.columns:
            df_inc = pd.DataFrame(columns=["Date", "Source", "Amount"])

        df_exp['Date'] = pd.to_datetime(df_exp['Date'], errors='coerce')
        df_inc['Date'] = pd.to_datetime(df_inc['Date'], errors='coerce')

        return df_exp, df_inc

    def save_row(sheet_object, tab_name, data):
        try:
            worksheet = sheet_object.worksheet(tab_name)
        except:
            worksheet = sheet_object.add_worksheet(title=tab_name, rows="1000", cols="10")
            if tab_name == "Expenses":
                worksheet.append_row(["Date", "Description", "Category", "Amount"])
            else:
                worksheet.append_row(["Date", "Source", "Amount"])
                
        worksheet.append_row(data)

    def delete_row(sheet_object, tab_name, row_index):
        worksheet = sheet_object.worksheet(tab_name)
        worksheet.delete_rows(row_index + 2)

    # --- LOAD DATA ---
    df_expenses, df_income = load_data(sh)

    if 'success_msg' in st.session_state:
        st.success(st.session_state['success_msg'])
        del st.session_state['success_msg']

    st.title(f"💰 {st.session_state['username'].capitalize()}'s Budget")

    # --- TABS ---
    tab1, tab2, tab3 = st.tabs(["📥 Add Income", "💸 Add Expense", "📊 Analytics"])

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

    with tab3:
        st.header("Spending Analysis")
        all_dates = pd.concat([df_income['Date'], df_expenses['Date']]).dropna()
        
        if not all_dates.empty:
            view_mode = st.radio("Select View Mode:", ["Monthly", "Annual"], horizontal=True)
            f_inc, f_exp = df_income.copy(), df_expenses.copy()
            
            # --- FILTER LOGIC ---
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
            
            # Sort by Date (Newest First)
            f_inc = f_inc.sort_values(by="Date", ascending=False)
            f_exp = f_exp.sort_values(by="Date", ascending=False)

            # --- TOP METRICS ---
            tot_inc = f_inc['Amount'].sum()
            tot_exp = f_exp['Amount'].sum()
            balance = tot_inc - tot_exp
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Income", f"RM {tot_inc:,.2f}")
            c2.metric("Total Expenses", f"RM {tot_exp:,.2f}")
            c3.metric("Balance", f"RM {balance:,.2f}")
            st.divider()

            # --- CHARTS ---
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

            # --- DETAILED RECORDS (Neat Grid + Download) ---
            with st.expander("Show Detailed Transaction Records", expanded=True):
                
                # 1. DOWNLOAD BUTTONS
                d_col1, d_col2 = st.columns(2)
                with d_col1:
                    csv_exp = f_exp.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download Expenses (CSV)", data=csv_exp, file_name=f"expenses_{view_mode}.csv", mime="text/csv")
                with d_col2:
                    csv_inc = f_inc.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download Income (CSV)", data=csv_inc, file_name=f"income_{view_mode}.csv", mime="text/csv")

                st.markdown("---")

                # 2. NEAT TRANSACTION GRID
                list_col_l, list_col_r = st.columns(2)

                # EXPENSES LIST
                with list_col_l:
                    st.subheader("Expenses List")
                    # Header Row
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
                            st.rerun()

                # INCOME LIST
                with list_col_r:
                    st.subheader("Income List")
                    # Header Row
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
                            st.rerun()
        else:
            st.info("No data found.")