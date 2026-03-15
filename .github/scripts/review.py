import os
import sys

import requests

# --- Get API Key from environment variables passed from GitHub Action ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DIFF_FILE_PATH = "pr_diff.txt"  # Define the path of the file to read

# --- Exit early if API Key is missing ---
if not GEMINI_API_KEY:
    print("Error: Environment variable GEMINI_API_KEY is not set.", file=sys.stderr)
    sys.exit(1)

# --- Read diff content from the file ---
try:
    with open(DIFF_FILE_PATH, encoding="utf-8") as f:
        PR_DIFF = f.read()
except FileNotFoundError:
    print(f"Error: Diff file not found at {DIFF_FILE_PATH}", file=sys.stderr)
    sys.exit(1)

if not PR_DIFF:
    print("Diff file is empty, no content to review.", file=sys.stderr)
    sys.exit(0)  # Exit normally

# Inform the AI in the prompt that the content may be truncated
prompt = f"""
Please act as a senior software engineer and respond in English.
Please review the following code changes (in git diff format) and provide constructive feedback 
on code quality, potential bugs, and best practices.
Please note: For brevity, the provided diff content may be truncated.
This is the code diff content:

{PR_DIFF}
"""

payload = {"contents": [{"parts": [{"text": prompt}]}]}
headers = {"Content-Type": "application/json"}
api_url = (
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
)


# --- Debugging: Print request details (excluding sensitive key) ---
print("--- Calling Gemini API ---", file=sys.stderr)
print(f"URL: {api_url.split('?')[0]}", file=sys.stderr)  # Print URL without key
print(f"Headers: {headers}", file=sys.stderr)

try:
    response = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=180,  # Increase timeout for larger prompts
    )
    # Check for HTTP errors specifically
    response.raise_for_status()

    response_json = response.json()
    review_comment = response_json["candidates"][0]["content"]["parts"][0]["text"]
    print(review_comment)

except requests.exceptions.HTTPError as e:
    print("--- HTTP Error ---", file=sys.stderr)
    print(f"Error: Received status code {e.response.status_code}", file=sys.stderr)
    print(f"Full API response: {e.response.text}", file=sys.stderr)
    sys.exit(1)
except requests.exceptions.RequestException as e:
    print("--- Network Error ---", file=sys.stderr)
    print(f"Error: Failed to call Gemini API due to a network issue: {e}", file=sys.stderr)
    sys.exit(1)
except (KeyError, IndexError) as e:
    print("--- Response Parse Error ---", file=sys.stderr)
    print(f"Error: Failed to parse Gemini API response: {e}", file=sys.stderr)
    print(f"Full API response: {response.text}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print("--- An Unexpected Error Occurred ---", file=sys.stderr)
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
