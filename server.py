from flask import Flask, request, jsonify
import openai
import requests
import os

app = Flask(__name__)

# Load environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MARKETO_CLIENT_ID = os.getenv("MARKETO_CLIENT_ID")
MARKETO_CLIENT_SECRET = os.getenv("MARKETO_CLIENT_SECRET")
MARKETO_BASE_URL = os.getenv("MARKETO_BASE_URL")
MARKETO_ACCESS_TOKEN = "8aecc22e-c75a-409b-b2f6-ff38fb79682a:ab"  # Replace with a valid token

@app.route("/")
def home():
    """Confirm the app is running."""
    return "Marketo Webhook is running!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Handles webhook requests from Marketo."""
    try:
        data = request.json  # Parse JSON payload
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        email = data.get("Email")
        first_name = data.get("FirstName", "")
        last_name = data.get("LastName", "")
        company = data.get("Company")

        if not email or not company:
            return jsonify({"error": "Missing required fields (Email, Company)"}), 400

        # Log received data
        print(f"Received: email={email}, company={company}")

        # Get company details from OpenAI
        company_info = get_company_info(company)

        # Extract fields
        industry = company_info.get("GPT_Industry__c", "Unknown")
        revenue = company_info.get("GPT_Revenue__c", "Unknown")
        company_size = company_info.get("GPT_Company_Size__c", "Unknown")
        company_fit = company_info.get("GPT_Fit_Assessment__c", "Unknown")

        # Send enriched data to Marketo
        marketo_response = update_marketo(email, first_name, last_name, industry, revenue, company_size, company_fit)

        return jsonify({
            "success": True,
            "marketo_response": marketo_response
        })

    except Exception as e:
        print(f"Webhook Error: {e}")
        return jsonify({"error": str(e)}), 500

def get_company_info(company_name):
    """Fetch company info using OpenAI."""
    prompt = f"""
    Find the following details for this company: {company_name}
    
    - GPT_Industry__c: The primary industry sector.
    - GPT_Revenue__c: Estimated annual revenue.
    - GPT_Company_Size__c: Provide one range: ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10,000", "10,000+"]
    - GPT_Fit_Assessment__c: A short blurb (1-2 sentences) about the company's fit.

    Respond in JSON format:
    {{
      "GPT_Industry__c": "...",
      "GPT_Revenue__c": "...",
      "GPT_Company_Size__c": "...",
      "GPT_Fit_Assessment__c": "..."
    }}
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            api_key=OPENAI_API_KEY
        )
        company_info = response['choices'][0]['message']['content']
        return eval(company_info)  # Convert JSON string to dictionary
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return {
            "GPT_Industry__c": "Unknown",
            "GPT_Revenue__c": "Unknown",
            "GPT_Company_Size__c": "Unknown",
            "GPT_Fit_Assessment__c": "Unknown"
        }

def update_marketo(email, first_name, last_name, industry, revenue, company_size, company_fit):
    """Send enriched data to Marketo."""
    try:
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
                    "GPT_Fit_Assessment__c": company_fit
                }
            ]
        }
        headers = {
            "Authorization": f"Bearer {MARKETO_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        response = requests.post(f"{MARKETO_BASE_URL}/rest/v1/leads.json", json=payload, headers=headers)
        return response.json()
    except Exception as e:
        print(f"Marketo API Error: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
