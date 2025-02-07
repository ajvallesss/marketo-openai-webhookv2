import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Load API credentials from environment variables
MARKETO_CLIENT_ID = os.getenv("MARKETO_CLIENT_ID")
MARKETO_CLIENT_SECRET = os.getenv("MARKETO_CLIENT_SECRET")
MARKETO_BASE_URL = os.getenv("MARKETO_BASE_URL")  # Example: "https://841-CLM-681.mktorest.com"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # OpenAI API key
MARKETO_ACCESS_TOKEN = None  # Will be retrieved dynamically

def get_marketo_access_token():
    """Retrieve a new Marketo access token."""
    global MARKETO_ACCESS_TOKEN

    url = f"{MARKETO_BASE_URL}/oauth/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": MARKETO_CLIENT_ID,
        "client_secret": MARKETO_CLIENT_SECRET,
    }
    
    response = requests.post(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        MARKETO_ACCESS_TOKEN = data.get("access_token")
        return MARKETO_ACCESS_TOKEN
    else:
        print(f"Failed to get Marketo token: {response.json()}")
        return None

def enrich_data_with_openai(data):
    """Send data to OpenAI and enrich it with GPT fields."""
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        openai_payload = {
            "model": "gpt-4",  # Use appropriate GPT model
            "messages": [
                {"role": "system", "content": "You are a B2B data enrichment assistant."},
                {"role": "user", "content": f"Enrich the following company data:\n{json.dumps(data, indent=2)}"}
            ]
        }

        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=openai_payload)

        if response.status_code == 200:
            gpt_response = response.json()
            enriched_data = json.loads(gpt_response["choices"][0]["message"]["content"])

            # Ensure only expected fields are returned
            return {
                "GPT_Revenue__c": enriched_data.get("GPT_Revenue__c", ""),
                "GPT_Industry__c": enriched_data.get("GPT_Industry__c", ""),
                "GPT_Fit_Assessment__c": enriched_data.get("GPT_Fit_Assessment__c", ""),
                "GPT_Company_Size__c": enriched_data.get("GPT_Company_Size__c", "")
            }
        else:
            print(f"OpenAI API Error: {response.json()}")
            return {}

    except Exception as e:
        print(f"Error enriching data with OpenAI: {str(e)}")
        return {}

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle webhook from Marketo, enrich data with OpenAI, and send back to Marketo."""
    global MARKETO_ACCESS_TOKEN

    if not MARKETO_ACCESS_TOKEN:
        MARKETO_ACCESS_TOKEN = get_marketo_access_token()
    
    if not MARKETO_ACCESS_TOKEN:
        return jsonify({"error": "Unable to retrieve Marketo access token"}), 500

    try:
        data = request.json
        marketo_url = f"{MARKETO_BASE_URL}/rest/v1/leads.json"

        headers = {
            "Authorization": f"Bearer {MARKETO_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        # Enrich data using OpenAI
        enriched_data = enrich_data_with_openai(data)

        # Combine original Marketo fields with enriched GPT fields
        marketo_data = {
            "action": "createOrUpdate",
            "lookupField": "email",
            "input": [{
                "Email": data.get("email"),
                "FirstName": data.get("first_name"),  # Corrected field name
                "LastName": data.get("last_name"),    # Corrected field name
                "Company": data.get("company"),
                **enriched_data  # Add GPT-enriched fields
            }]
        }

        # Send enriched data back to Marketo
        response = requests.post(marketo_url, headers=headers, json=marketo_data)
        marketo_response = response.json()

        # Handle token expiration and retry if needed
        if "errors" in marketo_response and marketo_response["errors"][0]["code"] == "601":
            MARKETO_ACCESS_TOKEN = get_marketo_access_token()  # Refresh token
            headers["Authorization"] = f"Bearer {MARKETO_ACCESS_TOKEN}"
            response = requests.post(marketo_url, headers=headers, json=marketo_data)
            marketo_response = response.json()

        return jsonify({"marketo_response": marketo_response, "success": True})

    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
