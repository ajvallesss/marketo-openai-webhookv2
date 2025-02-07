from flask import Flask, request, jsonify
import openai
import requests
import os
import json
import re
import time

app = Flask(__name__)

# Load environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MARKETO_CLIENT_ID = os.getenv("MARKETO_CLIENT_ID")
MARKETO_CLIENT_SECRET = os.getenv("MARKETO_CLIENT_SECRET")
MARKETO_BASE_URL = os.getenv("MARKETO_BASE_URL")

# Store Marketo token with expiry
MARKETO_ACCESS_TOKEN = None
MARKETO_TOKEN_EXPIRY = 0  # Unix timestamp

# Cache for company data (prevents inconsistencies)
COMPANY_CACHE = {}

# Standardized Revenue & Employee Size Ranges
REVENUE_BUCKETS = {
    "Under $1M": "<$1M",
    "$1M-$10M": "$1M - $10M",
    "$10M-$50M": "$10M - $50M",
    "$50M-$100M": "$50M - $100M",
    "$100M-$500M": "$100M - $500M",
    "$500M-$1B": "$500M - $1B",
    "$1B-$10B": "$1B - $10B",
    "$10B+": "$10B+"
}

EMPLOYEE_BUCKETS = {
    "1-10": "1-10",
    "11-50": "11-50",
    "51-200": "51-200",
    "201-500": "201-500",
    "501-1000": "501-1000",
    "1001-5000": "1001-5000",
    "5001-10000": "5001-10000",
    "10000+": "10000+"
}

def get_marketo_access_token():
    """Fetch a new Marketo access token if expired."""
    global MARKETO_ACCESS_TOKEN, MARKETO_TOKEN_EXPIRY

    if time.time() < MARKETO_TOKEN_EXPIRY:
        return MARKETO_ACCESS_TOKEN  

    print("🔄 Fetching new Marketo access token...")

    token_url = f"{MARKETO_BASE_URL}/identity/oauth/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": MARKETO_CLIENT_ID,
        "client_secret": MARKETO_CLIENT_SECRET
    }

    try:
        response = requests.get(token_url, params=params)
        response.raise_for_status()
        token_data = response.json()

        MARKETO_ACCESS_TOKEN = token_data["access_token"]
        MARKETO_TOKEN_EXPIRY = time.time() + token_data["expires_in"] - 60  

        print("✅ New Marketo Token Acquired")
        return MARKETO_ACCESS_TOKEN
    except Exception as e:
        print(f"🚨 Marketo Token Error: {e}")
        return None

@app.route("/")
def home():
    """Confirm the app is running."""
    return "Marketo Webhook is running!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Handles webhook requests from Marketo."""
    try:
        raw_request_data = request.data.decode("utf-8")
        print(f"Raw Request Data: {raw_request_data}")

        cleaned_data = re.sub(r'""([^""]*)""', r'"\1"', raw_request_data)

        if not request.is_json:
            return jsonify({"error": "Unsupported Media Type. Expected application/json"}), 415

        try:
            data = json.loads(cleaned_data)
        except json.JSONDecodeError as e:
            print(f"🚨 JSON Parsing Error: {e}")
            return jsonify({"error": "Invalid JSON format"}), 400

        email = data.get("email") or data.get("Email")
        first_name = data.get("first_name") or data.get("FirstName", "")
        last_name = data.get("last_name") or data.get("LastName", "")
        company = data.get("company") or data.get("Company")

        if not email or not company:
            return jsonify({"error": "Missing required fields (email, company)"}), 400

        print(f"✅ Received: email={email}, company={company}")

        company_info = get_company_info(company, email)

        industry = company_info.get("GPT_Industry__c", "Unknown")
        revenue = company_info.get("GPT_Revenue__c", "Unknown")
        company_size = company_info.get("GPT_Company_Size__c", "Unknown")
        fit_assessment = company_info.get("GPT_Fit_Assessment__c", "Unknown")

        print(f"🧠 OpenAI Response: {company_info}")

        marketo_response = update_marketo(email, first_name, last_name, industry, revenue, company_size, fit_assessment)

        print(f"📨 Marketo Response: {marketo_response}")

        return jsonify({"success": True, "marketo_response": marketo_response})

    except Exception as e:
        print(f"🚨 Webhook Error: {e}")
        return jsonify({"error": str(e)}), 500

def get_company_info(company_name, email=None):
    """Fetch company info using OpenAI, ensuring consistency and standardization."""

    domain = email.split("@")[-1] if email and "@" in email else None

    if company_name in COMPANY_CACHE:
        print(f"✅ Using Cached Data for {company_name}")
        return COMPANY_CACHE[company_name]

    prompt = f"""
    You are an AI assistant that retrieves company data from reputable sources like LinkedIn, Google, and Crunchbase.

    **Company Name**: {company_name}
    **Domain (if available)**: {domain}

    **Return the following standardized information:**
    - **GPT_Industry__c**: The company's primary industry.
    - **GPT_Revenue__c**: Select one range: {list(REVENUE_BUCKETS.keys())}
    - **GPT_Company_Size__c**: Select one range: {list(EMPLOYEE_BUCKETS.keys())}
    - **GPT_Fit_Assessment__c**: Is this company a **good fit for Coalesce.io**? If yes, explain why in 1-2 sentences. If no, explain why.

    **DO NOT RETURN "UNKNOWN" OR "NONE". Infer information if needed.**
    
    **Respond in strict JSON format without additional text:**
    {{
      "GPT_Industry__c": "...",
      "GPT_Revenue__c": "...",
      "GPT_Company_Size__c": "...",
      "GPT_Fit_Assessment__c": "..."
    }}
    """

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )

        company_info = json.loads(response.choices[0].message.content)

        company_info["GPT_Revenue__c"] = REVENUE_BUCKETS.get(company_info["GPT_Revenue__c"], "Unknown")
        company_info["GPT_Company_Size__c"] = EMPLOYEE_BUCKETS.get(company_info["GPT_Company_Size__c"], "Unknown")

        COMPANY_CACHE[company_name] = company_info
        print(f"🧠 Cached Company Data: {company_info}")

        return company_info

    except Exception as e:
        print(f"🚨 OpenAI Error: {e}")
        return {"GPT_Industry__c": "Unknown", "GPT_Revenue__c": "Unknown", "GPT_Company_Size__c": "Unknown", "GPT_Fit_Assess
