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

    token_url = f"{MARKETO
