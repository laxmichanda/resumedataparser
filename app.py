# app.py
import os
import requests
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from resume_parser import extract_text_from_pdf, extract_text_from_image, extract_resume_info
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Google Sheets Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("ResumeData").sheet1  # Change to your sheet name

# Add column headers if sheet is empty
def ensure_headers():
    """Add column headers if the sheet is empty."""
    try:
        if sheet.row_count < 2:  # Only header or empty
            # Check if first row has headers
            first_row = sheet.row_values(1)
            if not first_row or first_row[0] != "Full Name":
                sheet.append_row([
                    "Full Name",
                    "Email",
                    "Phone Number",
                    "CGPA",
                    "BTech College Name"
                ])
                print("[INFO] Added column headers to Google Sheet")
    except Exception as e:
        print(f"[HEADER ERROR] {e}")

# Ensure headers exist
ensure_headers()

@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return "✅ WhatsApp Resume Parser is running! Send a resume via WhatsApp."

@app.route("/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    """Webhook to handle incoming WhatsApp messages via Twilio."""
    print("twilio webhook triggered")
    if request.method == "GET":
        # Webhook verification for Twilio
        return "Webhook verified"
    
    msg = request.form.get("Body", "").lower()
    num_media = int(request.form.get("NumMedia", 0))
    resp = MessagingResponse()

    if num_media > 0:
        import time
        
        media_url = request.form.get("MediaUrl0")
        content_type = request.form.get("MediaContentType0", "")
        
        # Create unique filename with timestamp to avoid overwriting
        timestamp = int(time.time())
        file_extension = content_type.split("/")[-1]
        
        # Handle PDF and common image formats
        if "pdf" in content_type.lower():
            file_extension = "pdf"
        elif "png" in content_type.lower():
            file_extension = "png"
        elif "jpeg" in content_type.lower() or "jpg" in content_type.lower():
            file_extension = "jpg"
            
        file_name = f"resume_{timestamp}.{file_extension}"
        file_path = os.path.join("downloads", file_name)
        os.makedirs("downloads", exist_ok=True)

        print(f"[DEBUG] Downloading file: {file_name}")
        print(f"[DEBUG] Content type: {content_type}")
        print(f"[DEBUG] Detected extension: {file_extension}")
        print(f"[DEBUG] Media URL: {media_url}")
        
        # Download the media file with Twilio authentication
        # Twilio media URLs require Basic Auth with Account SID and Auth Token
        account_sid = os.getenv("TWILIO_ACCOUNT_SID") or request.form.get("AccountSid")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        
        print(f"[DEBUG] Account SID: {account_sid[:10]}..." if account_sid else "[DEBUG] No Account SID")
        print(f"[DEBUG] Auth Token available: {'Yes' if auth_token else 'No'}")
        
        if account_sid and auth_token:
            print("[DEBUG] Using Twilio authentication...")
            auth = (account_sid, auth_token)
            r = requests.get(media_url, auth=auth)
        else:
            print("[DEBUG] WARNING: No Twilio credentials. Media download may fail.")
            print("[DEBUG] Trying without auth...")
            r = requests.get(media_url)
        
        print(f"[DEBUG] Download response status: {r.status_code}")
        
        if r.status_code != 200:
            print(f"[ERROR] Failed to download media. Status: {r.status_code}")
            print(f"[ERROR] Response: {r.text[:200]}")
            resp.message(f"❌ Error downloading resume: HTTP {r.status_code}. Check Twilio credentials.")
            return str(resp)
            
        with open(file_path, "wb") as f:
            f.write(r.content)

        print(f"[DEBUG] File saved. Size: {os.path.getsize(file_path)} bytes")
        
        # Extract text based on file type
        text = ""
        try:
            if file_extension.lower() == "pdf" or file_name.lower().endswith(".pdf"):
                print("[DEBUG] Attempting PDF extraction...")
                text = extract_text_from_pdf(file_path)
                print(f"[DEBUG] PDF extracted text length: {len(text)} characters")
                
                # If PDF extraction returns little or no text, it might be a scanned/image PDF
                # Try OCR as fallback
                if len(text.strip()) < 50:  # Very little text extracted
                    print("[DEBUG] PDF returned minimal text, trying OCR as fallback...")
                    try:
                        ocr_text = extract_text_from_image(file_path)
                        if len(ocr_text.strip()) > len(text.strip()):
                            print(f"[DEBUG] OCR found more text ({len(ocr_text)} chars), using OCR result")
                            text = ocr_text
                        else:
                            print(f"[DEBUG] OCR didn't help, keeping PDF extraction ({len(text)} chars)")
                    except Exception as ocr_error:
                        print(f"[DEBUG] OCR fallback failed: {ocr_error}, using PDF result")
                else:
                    print(f"[DEBUG] PDF extraction successful")
            else:
                print("[DEBUG] Attempting image/OCR extraction...")
                text = extract_text_from_image(file_path)
            
            print(f"[DEBUG] Final extracted text length: {len(text)} characters")
            print(f"[DEBUG] First 500 chars of text: {text[:500]}")
            
            if not text or len(text.strip()) == 0:
                print("[ERROR] No text could be extracted from the file!")
                resp.message("❌ Could not extract text from the resume. Please ensure the file is not corrupted.")
                return str(resp)
        except Exception as e:
            print(f"[ERROR] Extraction failed: {e}")
            import traceback
            traceback.print_exc()
            resp.message(f"❌ Error processing resume: {str(e)}")
            return str(resp)
        
        data = extract_resume_info(text)
        print(f"[DEBUG] Extracted data: {data}")

        # Add to Google Sheets
        try:
            sheet.append_row([
                data.get("Full Name", "N/A"),
                data.get("Email", "N/A"),
                data.get("Phone Number", "N/A"),
                data.get("CGPA", "N/A"),
                data.get("BTech College Name", "N/A")
            ])
        except Exception as e:
            print(f"[SHEET ERROR] {e}")

        resp.message(f"✅ Resume processed successfully!\n\nExtracted info:\n{data}")
    else:
        # Handle text-only messages
        body = request.form.get("Body", "")
        
        if body and len(body.strip()) > 10:
            print(f"[DEBUG] Received text message: {len(body)} characters")
            print(f"[DEBUG] First 200 chars: {body[:200]}")
            
            # Check if it looks like a resume text
            if any(keyword in body.lower() for keyword in ['email', '@', 'mobile', 'phone', 'cgpa', 'college', 'b.tech', 'education']):
                print("[DEBUG] Looks like a resume text, processing...")
                
                # Extract info from plain text using Gemini
                data = extract_resume_info(body)
                print(f"[DEBUG] Extracted data: {data}")
                
                # Add to Google Sheets
                try:
                    sheet.append_row([
                        data.get("Full Name", "N/A"),
                        data.get("Email", "N/A"),
                        data.get("Phone Number", "N/A"),
                        data.get("CGPA", "N/A"),
                        data.get("BTech College Name", "N/A")
                    ])
                except Exception as e:
                    print(f"[SHEET ERROR] {e}")
                
                resp.message(f"✅ Resume processed successfully!\n\nExtracted info:\n{data}")
            else:
                resp.message("📄 Please send a resume text or PDF/image. The message should contain: name, email, phone, CGPA, and college name.")
        else:
            resp.message("📄 Please send a resume as text, PDF, or image to extract details.")

    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)