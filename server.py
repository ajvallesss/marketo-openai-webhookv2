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

def get_marketo_access_token():
    """Fetch a new Marketo access token if expired."""
    global MARKETO_ACCESS_TOKEN, MARKETO_TOKEN_EXPIRY

    if time.time() < MARKETO_TOKEN_EXPIRY:
        return MARKETO_ACCESS_TOKEN  # Return cached token if still valid

    print("🔄 Fetching new Marketo access token...")

    token_url = f"{MARKETO_BASE_URL}/identity/oauth/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": MARKETO_CLIENT_ID,
        "client_secret": MARKETO_CLIENT_SECRET
    }

    try:
        response = requests.get(token_url, params=params)
        response.raise_for_status()  # Raise error if request fails
        token_data = response.json()

        MARKETO_ACCESS_TOKEN = token_data["access_token"]
        MARKETO_TOKEN_EXPIRY = time.time() + token_data["expires_in"] - 60  # Buffer time

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
        # Log raw request for debugging
        raw_request_data = request.data.decode("utf-8")
        print(f"Raw Request Data: {raw_request_data}")

        # Clean extra double quotes
        cleaned_data = re.sub(r'""([^""]*)""', r'"\1"', raw_request_data)

        # Ensure request is JSON
        if not request.is_json:
            return jsonify({"error": "Unsupported Media Type. Expected application/json"}), 415

        # Attempt to parse JSON safely
        try:
            data = json.loads(cleaned_data)
        except json.JSONDecodeError as e:
            print(f"🚨 JSON Parsing Error: {e}")
            return jsonify({"error": "Invalid JSON format"}), 400

        # Normalize field names
        email = data.get("email") or data.get("Email")
        first_name = data.get("first_name") or data.get("FirstName", "")
        last_name = data.get("last_name") or data.get("LastName", "")
        company = data.get("company") or data.get("Company")

        if not email or not company:
            return jsonify({"error": "Missing required fields (email, company)"}), 400

        print(f"✅ Received: email={email}, company={company}")

        # Get enriched company details from OpenAI
        company_info = get_company_info(company)

        # Extract OpenAI-generated fields
        industry = company_info.get("GPT_Industry__c", "Unknown")
        revenue = company_info.get("GPT_Revenue__c", "Unknown")
        company_size = company_info.get("GPT_Company_Size__c", "Unknown")
        fit_assessment = company_info.get("GPT_Fit_Assessment__c", "Unknown")

        print(f"🧠 OpenAI Response: {company_info}")

        # Send enriched data to Marketo
        marketo_response = update_marketo(email, first_name, last_name, industry, revenue, company_size, fit_assessment)

        print(f"📨 Marketo Response: {marketo_response}")

        return jsonify({
            "success": True,
            "marketo_response": marketo_response
        })

    except Exception as e:
        print(f"🚨 Webhook Error: {e}")
        return jsonify({"error": str(e)}), 500


def get_company_info(company_name, email=None):
    """Fetch company info using OpenAI with function calling, and use domain if the company is not found."""

    # Extract domain from email if company details are missing
    domain = email.split("@")[-1] if email and "@" in email else None

    prompt = f"""
    You are an AI assistant with access to business intelligence data. Your task is to extract business information for the company: **"{company_name}"**.

    If the exact company is not found, **use the domain** "{domain}" (if available) and infer company details based on business directories, LinkedIn, Crunchbase, company websites, and news reports.

    **Provide the following details**:
    - **GPT_Industry__c**: The primary industry sector.
    - **GPT_Revenue__c**: Estimated annual revenue in USD (e.g., "$10M-$50M").
    - **GPT_Company_Size__c**: Employee count in these ranges: ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10,000", "10,000+"].
    - **GPT_Fit_Assessment__c**: A **short blurb (1-2 sentences)** about what this company does.

    **If no company data is found, infer details based on the domain and public data sources.**

    **Respond strictly in JSON format without any additional text**:
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
            model="gpt-4-turbo",  # NEWER, FASTER, CHEAPER MODEL
            messages=[{"role": "user", "content": prompt}],
            functions=[{
                "name": "get_company_info",
                "description": "Retrieves structured company information based on available business intelligence data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "GPT_Industry__c": {"type": "string"},
                        "GPT_Revenue__c": {"type": "string"},
                        "GPT_Company_Size__c": {"type": "string"},
                        "GPT_Fit_Assessment__c": {"type": "string"}
                    },
                    "required": ["GPT_Industry__c", "GPT_Revenue__c", "GPT_Company_Size__c", "GPT_Fit_Assessment__c"]
                }
            }],
            temperature=0.5
        )

        if not response.choices or not response.choices[0].message.function_call:
            print("🚨 OpenAI Function Call Failed!")
            raise ValueError("OpenAI did not return structured company data.")

        company_info = response.choices[0].message.function_call.arguments
        print(f"🧠 OpenAI Response: {company_info}")  # Log full response

        return json.loads(company_info)  # Convert JSON string to dictionary

    except Exception as e:
        print(f"🚨 OpenAI Error: {e}")
        return {
            "GPT_Industry__c": "Unknown",
            "GPT_Revenue__c": "Unknown",
            "GPT_Company_Size__c": "Unknown",
            "GPT_Fit_Assessment__c": "Unknown"
        }



def update_marketo(email, first_name, last_name, industry, revenue, company_size, fit_assessment):
    """Send enriched data to Marketo."""
    try:
        access_token = get_marketo_access_token()  # Ensure valid token

        if not access_token:
            return {"error": "Failed to retrieve Marketo access token"}

        payload = {
            "action": "createOrUpdate",
            "lookupField": "email",
            "input": [
                {
                    "Email": email,
                    "FirstName": first_name,
                    "LastName": last_name,
                    "GPT_Industry__c": industry,
                    "GPT_Revenue__c": revenue,
                    "GPT_Company_Size__c": company_size,
                    "GPT_Fit_Assessment__c": fit_assessment
                }
            ]
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = requests.post(f"{MARKETO_BASE_URL}/rest/v1/leads.json", json=payload, headers=headers)
        
        print(f"📨 Marketo Response: {response.status_code} {response.text}")

        return response.json()

    except Exception as e:
        print(f"🚨 Marketo API Error: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
