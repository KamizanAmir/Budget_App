import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import plotly.express as px

# --- CONFIGURATION ---
st.set_page_config(page_title="Family Budget Tracker", page_icon="🏠", layout="wide")

# --- CONNECT TO GOOGLE SHEETS (API) ---
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- USER MANAGEMENT FUNCTIONS ---
def check_login(username, password):
    """Checks credentials against the Master List."""
    client = get_client()
    try:
        user_sheet = client.open("Budget_App_Users").sheet1
        records = user_sheet.get_all_records()
        df_users = pd.DataFrame(records)
        
        # Look for the username
        user_row = df_users[df_users['Username'].astype(str) == str(username)]
        
        if not user_row.empty:
            stored_password = str(user_row.iloc[0]['Password'])
            if str(password) == stored_password:
                return user_row.iloc[0]['Sheet_Name']
    except Exception as e:
        st.error(f"Login System Error: {e}")
    return None

def register_user(username, password, sheet_name, user_email):
    """
    1. Checks if username exists.
    2. CREATES a new Google Sheet.
    3. Sets up Expenses/Income tabs.
    4. SHARES it with the user's email.
    5. Saves user to database.
    """
    client = get_client()
    
    # 1. Check if Username Exists
    try:
        master_sheet = client.open("Budget_App_Users").sheet1
        records = master_sheet.get_all_records()
        df_users = pd.DataFrame(records)
        if not df_users.empty and str(username) in df_users['Username'].astype(str).values:
            return False, "Username already taken."
    except:
        pass 

    # 2. AUTO-CREATE THE SHEET
    try:
        # Create the new sheet (The Bot is the Owner)
        new_sh = client.create(sheet_name)
        
        # 3. SHARE IT with the User (So they can see it too)
        # 'writer' permission means 'Editor' access
        new_sh.share(user_email, perm_type='user', role='writer')
        
        # 4. SETUP TABS & HEADERS
        # Create Expenses Tab
        ws_exp = new_sh.add_worksheet(title="Expenses", rows="1000", cols="10")
        ws_exp.append_row(["Date", "Description", "Category", "Amount"])
        
        # Create Income Tab
        ws_inc = new_sh.add_worksheet(title="Income", rows="1000", cols="10")
        ws_inc.append_row(["Date", "Source", "Amount"])
        
        # Create Settings Tab (For future password changes)
        ws_set = new_sh.add_worksheet(title="Settings", rows="10", cols="5")
        ws_set.append_row(["Key", "Value"])
        ws_set.append_row(["password", password]) # Backup password storage

        # Delete the default 'Sheet1' to keep it clean
        try:
            sheet1 = new_sh.worksheet("Sheet1")
            new_sh.del_worksheet(sheet1)
        except:
            pass
            
    except Exception as e:
        return False, f"Error creating sheet: {e}"

    # 5. SAVE TO DATABASE
    try:
        master_sheet.append_row([username, password, sheet_name])
        return True, f"Success! Sheet '{sheet_name}' created and shared with {user_email}."
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

# --- LOGIN / SIGN UP SCREEN ---
if st.session_state['user_sheet_name'] is None:
    st.title("🔐 Family Budget App")
    
    tab_login, tab_signup = st.tabs(["Login", "Create Account"])
    
    # --- TAB 1: LOGIN ---
    with tab_login:
        with st.form("login_form"):
            user_input = st.text_input("Username")
            pass_input = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Login")
            
            if submit_login:
                target_sheet = check_login(user_input, pass_input)
                if target_sheet:
                    st.session_state['user_sheet_name'] = target_sheet
                    st.session_state['username'] = user_input
                    st.success(f"Welcome back, {user_input}!")
                    st.rerun()
                else:
                    st.error("Invalid Username or Password")

    # --- TAB 2: CREATE ACCOUNT (Auto-Setup) ---
    with tab_signup:
        st.info("ℹ️ We will automatically create a Google Sheet for you and share it with your Gmail.")
        
        with st.form("signup_form"):
            new_user = st.text_input("Choose Username")
            new_pass = st.text_input("Choose Password", type="password")
            new_email = st.text_input("Your Gmail Address (To access your file)")
            sheet_name_input = st.text_input("Name for your new Sheet (e.g. Kamizan Budget)")
            
            submit_signup = st.form_submit_button("Create Account & Sheet")
            
            if submit_signup:
                if new_user and new_pass and sheet_name_input and new_email:
                    with st.spinner("🤖 Bot is creating your sheet... This takes about 10 seconds."):
                        success, message = register_user(new_user, new_pass, sheet_name_input, new_email)
                        if success:
                            st.success(message)
                        else:
                            st.error(message)
                else:
                    st.warning("Please fill in all fields.")
    
    st.stop() 

# ==========================================
#  MAIN APP (Runs only after login)
# ==========================================
try:
    client = get_client()
    sh = client.open(st.session_state['user_sheet_name']) 
except Exception as e:
    st.error(f"Error accessing budget file. ({e})")
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
    worksheet = sheet_object.worksheet(tab_name)
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