import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Load Marketo credentials from environment variables
MARKETO_CLIENT_ID = os.getenv("MARKETO_CLIENT_ID")
MARKETO_CLIENT_SECRET = os.getenv("MARKETO_CLIENT_SECRET")
MARKETO_BASE_URL = os.getenv("MARKETO_BASE_URL")  # Example: "https://841-CLM-681.mktorest.com"
MARKETO_ACCESS_TOKEN = os.getenv("MARKETO_ACCESS_TOKEN")

def get_marketo_access_token():
    """Retrieve a new Marketo access token if not set or expired."""
    global MARKETO_ACCESS_TOKEN

    if not MARKETO_CLIENT_ID or not MARKETO_CLIENT_SECRET or not MARKETO_BASE_URL:
        return None

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

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle webhook requests and send data to Marketo."""
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

        response = requests.post(marketo_url, headers=headers, json={"action": "createOrUpdate", "input": [data]})
        marketo_response = response.json()

        # Handle token expiration and retry
        if "errors" in marketo_response and marketo_response["errors"][0]["code"] == "601":
            MARKETO_ACCESS_TOKEN = get_marketo_access_token()  # Get a new token
            headers["Authorization"] = f"Bearer {MARKETO_ACCESS_TOKEN}"
            response = requests.post(marketo_url, headers=headers, json={"action": "createOrUpdate", "input": [data]})
            marketo_response = response.json()

        return jsonify({"marketo_response": marketo_response, "success": True})

    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
