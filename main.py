import os
from openpyxl import load_workbook
from datetime import datetime

FILE_NAME = "my_budget_data.xlsx"

def save_to_excel(sheet_name, data):
    """Opens the Excel file and appends a row to the specific sheet."""
    try:
        wb = load_workbook(FILE_NAME)
        ws = wb[sheet_name]
        ws.append(data) # Adds the list of data to the next empty row
        wb.save(FILE_NAME)
        print(f"✅ Successfully saved to {sheet_name}!")
    except Exception as e:
        print(f"❌ Error saving data: {e}")

def add_expense():
    print("\n--- 💸 Add New Expense ---")
    
    # 1. Get Date (Default to today if empty)
    date_input = input("Date (YYYY-MM-DD) [Press Enter for Today]: ")
    if date_input == "":
        date_input = datetime.now().strftime("%Y-%m-%d")
    
    # 2. Get Details
    description = input("Description (e.g., Nasi Lemak, Fuel): ")
    category = input("Category (e.g., Food, Transport, Utilities): ")
    
    # 3. Get Amount (Ensure it's a number)
    while True:
        try:
            amount = float(input("Amount: "))
            break
        except ValueError:
            print("Please enter a valid number for the amount.")

    # Prepare data based on columns: [Date, Description, Category, Amount]
    row_data = [date_input, description, category, amount]
    save_to_excel('Expenses', row_data)

def main():
    while True:
        print("\n" + "="*30)
        print("   PERSONAL BUDGET TRACKER")
        print("="*30)
        print("1. Add Expense")
        print("2. Add Income (Coming soon)")
        print("3. Exit")
        
        choice = input("\nSelect an option (1-3): ")
        
        if choice == '1':
            add_expense()
        elif choice == '2':
            print("We will build this in the next step!")
        elif choice == '3':
            print("Exiting system. Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()