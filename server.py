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

        print(f"🧠 OpenAI Response (Company Info): {company_info}")

        # Get enriched person details from OpenAI
        person_info = get_person_info(first_name, last_name, company, email)

        print(f"🕵️ OpenAI Response (Person Info): {person_info}")

        # Send enriched data to Marketo
        marketo_response = update_marketo(email, first_name, last_name, industry, revenue, company_size, fit_assessment)

        print(f"📨 Marketo Response: {marketo_response}")

        return jsonify({
            "success": True,
            "marketo_response": marketo_response,
            "person_info": person_info
        })

    except Exception as e:
        print(f"🚨 Webhook Error: {e}")
        return jsonify({"error": str(e)}), 500


def get_person_info(first_name, last_name, company, email):
    """Fetch personal contact insights using OpenAI."""
    
    prompt = f"""
    You are a research assistant. Your job is to find publicly available information on **{first_name} {last_name}**, who works at **{company}**.

    **Data Sources to Consider:**
    - LinkedIn profiles
    - The company's website (about/team page)
    - Other public sources like Twitter, blogs, or industry sites

    **Required JSON Output:**
    {{
      "LinkedIn_Profile": "LinkedIn URL if available, otherwise 'Not Found'",
      "Company_Website_Profile": "URL if they appear on their company's website, otherwise 'Not Found'",
      "Other_Relevant_Links": ["Any other public links that may be helpful"],
      "Notes": "Brief summary of their role or notable details (if available)"
    }}
    
    Ensure data is sourced from reliable places and avoid speculation.
    """

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            functions=[{
                "name": "get_person_info",
                "description": "Finds publicly available information about a person from professional sources.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "LinkedIn_Profile": {"type": "string"},
                        "Company_Website_Profile": {"type": "string"},
                        "Other_Relevant_Links": {"type": "array", "items": {"type": "string"}},
                        "Notes": {"type": "string"}
                    },
                    "required": ["LinkedIn_Profile", "Company_Website_Profile", "Other_Relevant_Links", "Notes"]
                }
            }],
            temperature=0.4
        )

        if not response.choices or not response.choices[0].message.function_call:
            print("🚨 OpenAI Function Call Failed!")
            raise ValueError("OpenAI did not return structured person data.")

        person_info = response.choices[0].message.function_call.arguments
        return json.loads(person_info)  # Ensure proper JSON parsing

    except Exception as e:
        print(f"🚨 OpenAI Error: {e}")
        return {
            "LinkedIn_Profile": "Not Found",
            "Company_Website_Profile": "Not Found",
            "Other_Relevant_Links": [],
            "Notes": "No details found"
        }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
