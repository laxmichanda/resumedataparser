# WhatsApp Resume Parser

Extract student information from resumes sent via WhatsApp using Twilio, Flask, and Google Gemini AI.

## Features

- 📱 **WhatsApp Integration** via Twilio
- 📄 **Multiple Input Formats:**
  - Plain text messages (paste resume text directly)
  - PDF files  
  - Image files (JPG, PNG)
- 🤖 **AI-Powered Extraction** using Google Gemini
- 📊 **Automatic Google Sheets Storage**
- 🔍 **Smart Text Detection** with OCR fallback
- 📋 **Auto-generated Column Headers**

## Extracted Information

1. **Full Name**
2. **Email**
3. **Phone Number**
4. **CGPA**
5. **BTech College Name**

## How to Use

### Option 1: Send Plain Text
Simply paste or type the resume content in WhatsApp:
```
DHANESH CHINTALA
Email: 22311a1217@it.sreenidhi.edu.in
Mobile: 9492704123
CGPA: 8.17
College: Sreenidhi Institute of Science and Technology
```

### Option 2: Send PDF or Image
Attach a resume PDF or image file in WhatsApp

## Setup

1. **Install Dependencies:**
```bash
pip install -r requirements.txt
```

2. **Configure:**
- Create `.env` file with Twilio credentials
- Add `credentials.json` for Google Sheets API
- Update Google Sheet name in `app.py` (line 20)

3. **Run:**
```bash
python app.py
```

4. **Start ngrok** (if running locally):
```bash
ngrok http 5000
```

5. **Configure Twilio Webhook** to point to your ngrok URL

## File Structure

- `app.py` - Flask webhook handler
- `resume_parser.py` - Text extraction and AI parsing
- `.env` - Environment variables (Twilio credentials)
- `credentials.json` - Google Sheets API credentials

## Google Sheet Format

| Full Name | Email | Phone Number | CGPA | BTech College Name |
|-----------|-------|--------------|------|-------------------|
| Auto-generated headers added on first run |

## Supported Resume Formats

- ✅ Plain text in WhatsApp message
- ✅ PDF files (with OCR fallback)
- ✅ Scanned PDF files (image-based)
- ✅ Image files (JPG, PNG)
- ✅ Structured/unstructured resumes

## Technologies Used

- Python 3
- Flask
- Twilio API
- Google Gemini AI
- Google Sheets API
- PDF parsing (pdfplumber)
- OCR (pytesseract)

