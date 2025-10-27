# resume_parser.py
import os
import json
import re
import pdfplumber
import pytesseract
from PIL import Image
import google.generativeai as genai

# Set up Gemini API key

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def pdf_to_images(file_path):
    """Convert PDF pages to images for OCR."""
    images = []
    try:
        from pdf2image import convert_from_path
        print(f"[PDF TO IMAGE] Converting PDF to images...")
        images = convert_from_path(file_path)
        print(f"[PDF TO IMAGE] Converted {len(images)} pages to images")
    except ImportError:
        print("[PDF TO IMAGE] pdf2image not installed, skipping PDF to image conversion")
    except Exception as e:
        print(f"[PDF TO IMAGE ERROR] {e}")
    return images

def extract_text_from_pdf(file_path):
    """Extract text from PDF using pdfplumber."""
    text = ""
    try:
        print(f"[PDF] Opening file: {file_path}")
        print(f"[PDF] File exists: {os.path.exists(file_path)}")
        print(f"[PDF] File size: {os.path.getsize(file_path)} bytes")
        
        with pdfplumber.open(file_path) as pdf:
            print(f"[PDF] Total pages: {len(pdf.pages)}")
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                print(f"[PDF] Page {i+1} text length: {len(page_text)}")
                text += page_text
                
        print(f"[PDF] Total text extracted: {len(text)} characters")
        
        # If PDF extraction returned very little text, it might be a scanned PDF
        if len(text.strip()) < 20:
            print("[PDF] Very little text extracted, trying OCR on PDF pages...")
            images = pdf_to_images(file_path)
            if images:
                for i, img in enumerate(images):
                    img_text = pytesseract.image_to_string(img)
                    print(f"[PDF OCR] Page {i+1} OCR text length: {len(img_text)}")
                    text += img_text
                print(f"[PDF OCR] Total OCR text: {len(text)} characters")
    except Exception as e:
        print(f"[PDF ERROR] {e}")
        import traceback
        traceback.print_exc()
        text = ""
    return text.strip()

def extract_text_from_image(file_path):
    """Extract text from an image using pytesseract."""
    try:
        print(f"[IMAGE] Opening file: {file_path}")
        print(f"[IMAGE] File exists: {os.path.exists(file_path)}")
        print(f"[IMAGE] File size: {os.path.getsize(file_path)} bytes")
        
        image = Image.open(file_path)
        print(f"[IMAGE] Image format: {image.format}, Size: {image.size}")
        
        # Try OCR with different configurations for better accuracy
        # First try with default config
        text = pytesseract.image_to_string(image, lang='eng')
        
        # If we got very little text, try with different config
        if len(text.strip()) < 10:
            print("[IMAGE] Retrying OCR with additional config...")
            custom_config = r'--oem 3 --psm 6'  # Assume a single uniform block of text
            text = pytesseract.image_to_string(image, config=custom_config)
        
        print(f"[IMAGE] Text extracted: {len(text)} characters")
    except Exception as e:
        print(f"[Image OCR ERROR] {e}")
        import traceback
        traceback.print_exc()
        text = ""
    return text.strip()

def extract_json_from_response(response_text):
    """Extract JSON object from AI response text."""
    try:
        cleaned_text = response_text.strip()
        
        # Try to parse directly if it's already valid JSON
        if cleaned_text.startswith("{") and cleaned_text.endswith("}"):
            try:
                return json.loads(cleaned_text)
            except json.JSONDecodeError:
                pass
        
        # Remove markdown code blocks if present
        cleaned_text = re.sub(r'```json\s*', '', cleaned_text)
        cleaned_text = re.sub(r'```\s*$', '', cleaned_text)
        cleaned_text = re.sub(r'^```\s*', '', cleaned_text)
        cleaned_text = cleaned_text.strip()
        
        # Try parsing again after removing markdown
        if cleaned_text.startswith("{") and cleaned_text.endswith("}"):
            try:
                return json.loads(cleaned_text)
            except json.JSONDecodeError:
                pass
        
        # Find the JSON object in the text using a more robust regex
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        json_matches = re.findall(json_pattern, cleaned_text, re.DOTALL)
        
        for match in json_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
        
        # If no JSON found, try to parse as raw text and extract fields manually
        print(f"[WARNING] Could not parse JSON from response. Trying manual extraction.")
        
        # Extract key-value pairs manually
        result = {}
        for field in ["Full Name", "Email", "Phone Number", "CGPA", "BTech College Name"]:
            pattern = rf'["\']?{field}["\']?\s*:\s*["\']?([^",\n]+)["\']?'
            match = re.search(pattern, cleaned_text, re.IGNORECASE)
            if match:
                result[field] = match.group(1).strip()
        
        return result if result else None
        
    except Exception as e:
        print(f"[JSON PARSING ERROR] {e}")
        return None

def extract_resume_info(text):
    """Use Gemini AI to extract structured info from resume text."""
    if not text:
        return {"error": "No text found in resume"}

    prompt = f"""
    You are a resume parser. Extract ONLY the following information from the resume text and return ONLY a valid JSON object with no additional text or comments. 

    Required JSON structure:
    {{
        "Full Name": "student's full name or N/A",
        "Email": "email address or N/A",
        "Phone Number": "mobile/phone number or N/A",
        "CGPA": "CGPA score (e.g., 9.47) or N/A",
        "BTech College Name": "college/institute name where BTech is being pursued or N/A"
    }}

    Critical instructions:
    - Extract ONLY these 5 fields. Do not extract skills, experience, or any other information.
    - Read the ENTIRE resume text from FIRST character to LAST character - scan every line thoroughly
    - Search EVERYWHERE in the text - emails and phone numbers could be:
      * In the header at the top
      * In a "Basic Information" or "Contact" section  
      * At the very bottom of the resume in footer
      * In the middle paragraphs
      * Near the name or in any section
      * In any format (with or without labels like "Mobile:", "Email:", "Phone:", etc.)
    - Look for ANY email pattern (@ symbol) anywhere in the document
    - Look for ANY phone number pattern (digits, with or without spaces, hyphens, parentheses) anywhere in the document
    - For CGPA: Search in "Academic Details", "Education", "B.Tech", or anywhere CGPA is mentioned
    - For College Name: Search in "Academic Details", "Education", B.Tech section, or institution name anywhere
    - For Name: Usually at the very top, but search throughout if not found
    - If information is in tabular/structured format, extract it from there too
    - Be thorough and check ALL parts of the text - nothing should be missed
    
    Resume Text:
    {text}

    Return ONLY the JSON object with no markdown, no explanations, no code blocks. Just pure JSON.
    """

    try:
        # Show how much text we're sending to AI
        print(f"[DEBUG] Total resume text length: {len(text)} characters")
        
        # Check if email and phone patterns exist in the text
        import re
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        phone_pattern = r'\b\d{10,}\b|[\d\s\-\(\)]{10,}'
        
        emails_found = re.findall(email_pattern, text)
        phones_found = re.findall(phone_pattern, text)
        
        print(f"[DEBUG] Emails found in text: {emails_found}")
        print(f"[DEBUG] Phone patterns found in text: {phones_found[:5]}")  # Show first 5
        
        # Only show last 500 chars if it's from a file (longer text), otherwise show first 500 for plain text
        if len(text) > 1000:
            print(f"[DEBUG] Last 500 chars of resume text: ...{text[-500:]}")
        else:
            print(f"[DEBUG] Full text (plain text message): {text[:1000]}")
        
        # Use a model that's definitely available (with models/ prefix)
        model = genai.GenerativeModel("models/gemini-flash-latest")
        print("[DEBUG] Using model: models/gemini-flash-latest")
        
        response = model.generate_content(prompt)
        print(f"[DEBUG] Response received, length: {len(response.text)}")
        
        # Try to extract JSON from the response
        parsed_data = extract_json_from_response(response.text)
        
        if parsed_data:
            return parsed_data
        else:
            # Fallback: return the raw response
            print(f"[PARSE FALLBACK] Response: {response.text[:200]}")
            return {
                "Full Name": "N/A",
                "Email": "N/A",
                "Phone Number": "N/A",
                "CGPA": "N/A",
                "BTech College Name": "N/A",
                "raw_response": response.text[:500]
            }
    except Exception as e:
        print(f"[GEMINI ERROR] {e}")
        return {"error": str(e)}