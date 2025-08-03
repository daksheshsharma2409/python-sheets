import gspread
from google.oauth2.service_account import Credentials

scopes = [
    "https://www.googleapis.com/auth/spreadsheets"
]

creds = Credentials.from_service_account_file("credentials.json", scopes = scopes)
client = gspread.authorize(creds)

sheet_id = "10rV0z0KIMJh1OKZVuewL8WtH4KR2m9zi3SMc_IoxzdI"

workbook = client.open_by_key(sheet_id)

sheet = workbook.worksheet("Sheet1")
value_list = workbook.sheet1.row_values(1)
head = ['Name', 'Date', 'Entry Time', 'Exit Time']
if value_list != head:
    sheet.update_cell(1, 1, "Name")
    sheet.update_cell(1, 2, "Date")
    sheet.update_cell(1, 3, "Entry Time")
    sheet.update_cell(1, 4, "Exit Time")
