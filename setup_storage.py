import pandas as pd
import os

# Define the file name
file_name = "my_budget_data.xlsx"

# 1. Define the structure based on your photos
# Expense Tracker (Image 1)
expenses_cols = ['Date', 'Description', 'Category', 'Amount']

# Income & Savings (Image 2)
income_cols = ['Date', 'Source', 'Amount']
savings_cols = ['Date', 'Description', 'Amount']

# Monthly Budget Goals (Image 3 - Categories)
# We will use this to set your limits for things like Housing, Food, etc.
budget_cols = ['Category', 'Budgeted_Amount']

# 2. Create empty DataFrames
df_expenses = pd.DataFrame(columns=expenses_cols)
df_income = pd.DataFrame(columns=income_cols)
df_savings = pd.DataFrame(columns=savings_cols)
df_budget = pd.DataFrame(columns=budget_cols)

# 3. Create the Excel file if it doesn't exist
if not os.path.exists(file_name):
    with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
        df_expenses.to_excel(writer, sheet_name='Expenses', index=False)
        df_income.to_excel(writer, sheet_name='Income', index=False)
        df_savings.to_excel(writer, sheet_name='Savings', index=False)
        df_budget.to_excel(writer, sheet_name='Budget_Plan', index=False)
    print(f"Success! '{file_name}' has been created with all the correct sheets.")
else:
    print(f"'{file_name}' already exists. No changes made.")