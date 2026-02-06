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
                    "BTech College Name",
                    "Skills"
                ])
                print("[INFO] Added column headers to Google Sheet")
    except Exception as e:
        print(f"[HEADER ERROR] {e}")

# Ensure headers exist
ensure_headers()

# Column indices (row 1 = header)
COL_FULL_NAME = 0
COL_EMAIL = 1
COL_PHONE = 2
COL_CGPA = 3
COL_COLLEGE = 4
COL_SKILLS = 5

def parse_cgpa(value):
    """Parse CGPA from cell value. Returns float or None if not a valid number."""
    if not value or value.strip().upper() in ("N/A", "NA", "-", ""):
        return None
    value = str(value).strip()
    # Handle "9.47/10" or "9.47" format
    if "/" in value:
        value = value.split("/")[0].strip()
    try:
        return float(value)
    except ValueError:
        return None

def get_shortlist(min_cgpa):
    """Return list of candidate rows (as dicts) from sheet where CGPA >= min_cgpa. Skips header."""
    try:
        rows = sheet.get_all_values()
        if len(rows) < 2:
            return []
        header = rows[0]
        shortlist = []
        for row in rows[1:]:
            if len(row) <= COL_CGPA:
                continue
            cgpa_val = parse_cgpa(row[COL_CGPA])
            if cgpa_val is not None and cgpa_val >= min_cgpa:
                shortlist.append({
                    "Full Name": row[COL_FULL_NAME] if len(row) > COL_FULL_NAME else "N/A",
                    "Email": row[COL_EMAIL] if len(row) > COL_EMAIL else "N/A",
                    "Phone Number": row[COL_PHONE] if len(row) > COL_PHONE else "N/A",
                    "CGPA": row[COL_CGPA],
                    "BTech College Name": row[COL_COLLEGE] if len(row) > COL_COLLEGE else "N/A",
                    "Skills": row[COL_SKILLS] if len(row) > COL_SKILLS else "N/A",
                })
        return shortlist
    except Exception as e:
        print(f"[SHORTLIST ERROR] {e}")
        return []

def create_shortlist_sheet(min_cgpa, candidates):
    """Create a new worksheet in ResumeData with the shortlist. Returns (sheet_url, sheet_title) or (None, None) on error."""
    try:
        from datetime import datetime
        spreadsheet = client.open("ResumeData")
        title = f"Shortlist_CGPA_{min_cgpa}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        new_sheet = spreadsheet.add_worksheet(title=title, rows=max(100, len(candidates) + 5), cols=6)
        headers = ["Full Name", "Email", "Phone Number", "CGPA", "BTech College Name", "Skills"]
        new_sheet.append_row(headers)
        for c in candidates:
            new_sheet.append_row([
                c.get("Full Name", "N/A"),
                c.get("Email", "N/A"),
                c.get("Phone Number", "N/A"),
                c.get("CGPA", "N/A"),
                c.get("BTech College Name", "N/A"),
                c.get("Skills", "N/A"),
            ])
        sheet_url = spreadsheet.url + "#gid=" + str(new_sheet.id)
        print(f"[INFO] Created shortlist sheet: {title}")
        return sheet_url, title
    except Exception as e:
        print(f"[SHORTLIST SHEET ERROR] {e}")
        import traceback
        traceback.print_exc()
        return None, None

@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return "✅ WhatsApp Resume Parser is running! Send a resume via WhatsApp. Shortlist: /shortlist?min_cgpa=8.0"

@app.route("/shortlist", methods=["GET"])
def shortlist_route():
    """Get candidates with CGPA >= min_cgpa. Query param: min_cgpa (e.g. 8.0)."""
    min_cgpa_str = request.args.get("min_cgpa", "").strip()
    if not min_cgpa_str:
        return "Usage: /shortlist?min_cgpa=8.0 (replace 8.0 with your minimum CGPA)", 400
    try:
        min_cgpa = float(min_cgpa_str)
    except ValueError:
        return "Invalid min_cgpa. Use a number, e.g. 8.0", 400
    candidates = get_shortlist(min_cgpa)
    sheet_url, sheet_title = create_shortlist_sheet(min_cgpa, candidates) if candidates else (None, None)
    if request.args.get("format") == "json":
        return {"min_cgpa": min_cgpa, "count": len(candidates), "candidates": candidates, "sheet_url": sheet_url, "sheet_title": sheet_title}
    # Simple HTML table
    lines = [f"<h2>Shortlist (CGPA &ge; {min_cgpa}) — {len(candidates)} candidate(s)</h2>"]
    if sheet_url:
        lines.append(f"<p><strong>New sheet created:</strong> <a href='{sheet_url}' target='_blank'>{sheet_title or 'Open sheet'}</a></p>")
    lines.append("<table border='1'><tr><th>Name</th><th>Email</th><th>Phone</th><th>CGPA</th><th>College</th><th>Skills</th></tr>")
    for c in candidates:
        lines.append(f"<tr><td>{c['Full Name']}</td><td>{c['Email']}</td><td>{c['Phone Number']}</td><td>{c['CGPA']}</td><td>{c['BTech College Name']}</td><td>{c['Skills']}</td></tr>")
    lines.append("</table>")
    return "\n".join(lines)

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
                data.get("BTech College Name", "N/A"),
                data.get("Skills", "N/A")
            ])
        except Exception as e:
            print(f"[SHEET ERROR] {e}")

        resp.message(f"✅ Resume processed successfully!\n\nExtracted info:\n{data}")
    else:
        # Handle text-only messages
        body = request.form.get("Body", "")
        body_lower = (body or "").strip().lower()

        # Shortlist command: "shortlist <min_cgpa> [count]" e.g. "shortlist 8.5 10" or "shortlist 8.5"
        if body_lower.startswith("shortlist "):
            parts = body_lower.replace("shortlist", "").strip().split()
            try:
                if not parts:
                    resp.message("📋 Use: shortlist 8.5 10 (min CGPA, then how many candidates)\nExample: shortlist 8.5 5")
                    return str(resp)
                min_cgpa = float(parts[0])
                # Optional: how many candidates to return (default 20)
                max_candidates = 20
                if len(parts) >= 2:
                    n = int(parts[1])
                    if n < 1:
                        n = 1
                    elif n > 50:
                        n = 50  # cap to avoid huge WhatsApp messages
                    max_candidates = n
                candidates = get_shortlist(min_cgpa)
                if not candidates:
                    resp.message(f"📋 No candidates found with CGPA ≥ {min_cgpa}.")
                else:
                    total = len(candidates)
                    show = candidates[:max_candidates]
                    # Create a new sheet with full shortlist and share link
                    sheet_url, sheet_title = create_shortlist_sheet(min_cgpa, candidates)
                    if sheet_url:
                        resp.message(f"📋 Shortlist sheet created: {sheet_title}\n🔗 Open: {sheet_url}")
                    if total < max_candidates:
                        header = f"📋 Shortlist (CGPA ≥ {min_cgpa}) — only {total} candidate(s) found (you asked for {max_candidates}):\n\n"
                    else:
                        header = f"📋 Shortlist (CGPA ≥ {min_cgpa}) — showing {len(show)} of {total}:\n\n"
                    # Build candidate lines and send in chunks (Twilio/WhatsApp ~4096 char limit)
                    MAX_CHARS_PER_MESSAGE = 3000
                    chunks = [header]
                    for i, c in enumerate(show, 1):
                        line = f"{i}. {c['Full Name']} — CGPA: {c['CGPA']}, {c['BTech College Name']}\n   📧 {c['Email']}\n"
                        if len(chunks[-1]) + len(line) > MAX_CHARS_PER_MESSAGE:
                            chunks.append(line)
                        else:
                            chunks[-1] += line
                    if total > max_candidates:
                        footer = f"\n({total - max_candidates} more. Full list in the sheet link above.)"
                        if len(chunks[-1]) + len(footer) <= MAX_CHARS_PER_MESSAGE:
                            chunks[-1] += footer
                        else:
                            chunks.append(footer)
                    for chunk in chunks:
                        resp.message(chunk)
                return str(resp)
            except (ValueError, IndexError):
                resp.message("📋 Use: shortlist 8.5 10 (min CGPA, then number of candidates)")
                return str(resp)

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
                        data.get("BTech College Name", "N/A"),
                        data.get("Skills", "N/A")
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