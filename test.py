import gspread
from oauth2client.service_account import ServiceAccountCredentials

scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("ResumeData").sheet1

# Add headers if they don't exist
if sheet.row_count == 0 or sheet.cell(1, 1).value != "Full Name":
    sheet.insert_row([
        "Full Name",
        "Email",
        "Phone Number",
        "CGPA",
        "BTech College Name"
    ], 1)
    print("✅ Headers added!")

# Optionally add a test row
# sheet.append_row(["John Doe", "john@example.com", "1234567890", "9.5", "MIT"])
# print("✅ Test data added!")
