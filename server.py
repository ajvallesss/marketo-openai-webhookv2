from flask import Flask, request, jsonify
import openai
import requests
import os

app = Flask(__name__)

# Load environment variables
OPENAI_API_KEY = os.getenv("openai_api_key")
MARKETO_CLIENT_ID = os.getenv("marketo_client_id")
MARKETO_CLIENT_SECRET = os.getenv("marketo_client_secret")
MARKETO_BASE_URL = os.getenv("marketo_base_url")

@app.route("/")
def home():
    """Root route to confirm the app is running."""
    return "Marketo Webhook is running!", 200

def get_company_info(company_name):
    """Call OpenAI to get GPT Industry, GPT Revenue, GPT Company Size (range), and GPT Company Fit (blurb)."""
    prompt = f"""
    Find the following details for this company: {company_name}
    
    - GPT Industry: The primary industry sector of the company.
    - GPT Revenue: Estimated annual revenue in USD.
    - GPT Company Size: Provide the estimated employee range. Choose from:
      ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10,000", "10,000+"]
    - GPT Company Fit: Provide a short blurb (1-2 sentences) explaining why this company is a good fit for enterprise B2B solutions.
    
    Respond in **JSON format**:
    {{
      "GPT Industry": "...",
      "GPT Revenue": "...",
      "GPT Company Size": "...",
      "GPT Company Fit": "..."
    }}
    """

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        api_key=OPENAI_API_KEY
    )

    try:
        company_info = response['choices'][0]['message']['content']
        return eval(company_info)  # Convert JSON string to dictionary
    except Exception:
        return {
            "GPT Industry": "Unknown",
            "GPT Revenue": "Unknown",
            "GPT Company Size": "Unknown",
            "GPT Company Fit": "Unknown"
        }

def update_marketo(email, first_name, last_name, industry, revenue, company_size, company_fit):
    """Send enriched data back to Marketo."""
    access_token = "your-marketo-access-token"  # Replace with a function to fetch dynamically

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

@app.route("/webhook", methods=["POST"])
def webhook():
    """Handles webhook request from Marketo."""
    data = request.json
    email = data.get("email")
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    company = data.get("company")

    if not email or not company:
        return jsonify({"error": "Missing required fields"}), 400

    # Get company information from OpenAI
    company_info = get_company_info(company)

    # Extract fields
    industry = company_info.get("GPT Industry", "Unknown")
    revenue = company_info.get("GPT Revenue", "Unknown")
    company_size = company_info.get("GPT Company Size", "Unknown")  # Now in ranges
    company_fit = company_info.get("GPT Company Fit", "Unknown")  # Now a short blurb

    # Send enriched data back to Marketo
    marketo_response = update_marketo(email, first_name, last_name, industry, revenue, company_size, company_fit)

    return jsonify({"success": True, "marketo
