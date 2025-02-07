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

        email = data.get("email")
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        company = data.get("company")

        if not email or not company:
            return jsonify({"error": "Missing required fields (email, company)"}), 400

        # Log received data
        print(f"Received: email={email}, company={company}")

        # Get company details from OpenAI
        company_info = get_company_info(company)

        # Extract fields
        industry = company_info.get("GPT Industry", "Unknown")
        revenue = company_info.get("GPT Revenue", "Unknown")
        company_size = company_info.get("GPT Company Size", "Unknown")
        company_fit = company_info.get("GPT Company Fit", "Unknown")

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
    
    - GPT Industry: The primary industry sector.
    - GPT Revenue: Estimated annual revenue.
    - GPT Company Size: Provide one range: ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10,000", "10,000+"]
    - GPT Company Fit: A short blurb (1-2 sentences) about the company's fit.

    Respond in JSON format:
    {{
      "GPT Industry": "...",
      "GPT Revenue": "...",
      "GPT Company Size": "...",
      "GPT Company Fit": "..."
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
            "GPT Industry": "Unknown",
            "GPT Revenue": "Unknown",
            "GPT Company Size": "Unknown",
            "GPT Company Fit": "Unknown"
        }

def update_marketo(email, first_name, last_name, industry, revenue, company_size, company_fit):
    """Send enriched data to Marketo."""
    try:
        access_token = "your-marketo-access-token"  # Replace with real token

        payload = {
            "action": "createOrUpdate",
            "lookupField": "email",
            "input": [
                {
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "GPT Industry": industry,
                    "GPT Revenue": revenue,
                    "GPT Company Size": company_size,
                    "GPT Company Fit": company_fit
                }
            ]
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = requests.post(f"{MARKETO_BASE_URL}/rest/v1/leads.json", json=payload, headers=headers)
        return response.json()

    except Exception as e:
        print(f"Marketo API Error: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
