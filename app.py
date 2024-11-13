from flask import Flask, request, jsonify, render_template
import os
import requests
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Flask app configuration
app = Flask(__name__)
UPLOAD_FOLDER = './uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# API keys
ZILLOW_API_KEY = os.getenv('ZILLOW_API_KEY')
REDFIN_API_KEY = os.getenv('REDFIN_API_KEY')
REALTOR_API_KEY = os.getenv('REALTOR_API_KEY')

# API configurations
APIS = {
    "Zillow": {
        "url": "https://zillow56.p.rapidapi.com/search_address",
        "payload": lambda property_info: {
            "params": {"address": property_info["address"]},
            "headers": {
                "x-rapidapi-key": ZILLOW_API_KEY,
                "x-rapidapi-host": "zillow56.p.rapidapi.com"
            }
        },
        "parser": lambda response: {
            "price": response.get("estimated_price", "N/A"),
            "status": response.get("status", "Unknown")
        }
    },
    "Redfin": {
        "urls": {
            "autocomplete": "https://redfin-base.p.rapidapi.com/redfin/locationAutocompletev2",
            "details": "https://redfin-base.p.rapidapi.com/redfin/details/estimate"
        },
        "payload": lambda property_info: {
            "autocomplete_params": {"location": property_info["address"]},
            "details_params": lambda property_id: {
                "propertyId": property_id,
                "listingId": "192155085"
            },
            "headers": {
                "x-rapidapi-key": REDFIN_API_KEY,
                "x-rapidapi-host": "redfin-base.p.rapidapi.com"
            }
        },
        "parser": lambda response: {
            "price": response["priceInfo"]["amount"] if response.get("isActivish") else "Off Market",
            "status": "Active" if response.get("isActivish") else "Not Active"
        }
    },
    "Realtor": {
        "urls": {
            "autocomplete": "https://realtor-com4.p.rapidapi.com/auto-complete",
            "details": "https://realtor-com4.p.rapidapi.com/properties/detail"
        },
        "payload": lambda property_info: {
            "autocomplete_params": {"input": property_info["address"]},
            "details_params": lambda property_id: {"property_id": property_id},
            "headers": {
                "x-rapidapi-key": REALTOR_API_KEY,
                "x-rapidapi-host": "realtor-com4.p.rapidapi.com"
            }
        },
        "parser": lambda response: {
            "price": response["home"]["list_price"] if "home" in response and "list_price" in response["home"] else "Off Market",
            "status": "Active" if "home" in response and "list_price" in response["home"] else "Not Active"
        }
    }
}

# Extract text from file
def extract_text(file_path):
    with open(file_path, 'r') as file:
        return file.read()

# Fetch data for each API individually
def fetch_property_data(service, config, property_info):
    try:
        if service in ["Redfin", "Realtor"]:
            # Two-step API process
            payload = config["payload"](property_info)
            autocomplete_response = requests.get(
                config["urls"]["autocomplete"],
                headers=payload["headers"],
                params=payload["autocomplete_params"],
                timeout=10
            )
            autocomplete_response.raise_for_status()
            autocomplete_data = autocomplete_response.json()
            property_id = (
                autocomplete_data.get("data", [{}])[0].get("mpr_id")
                if service == "Realtor" else
                autocomplete_data.get("data", [{}])[0].get("propertyId")
            )
            if not property_id:
                return {"service": service, "error": "Property ID not found"}

            details_response = requests.get(
                config["urls"]["details"],
                headers=payload["headers"],
                params=payload["details_params"](property_id),
                timeout=10
            )
            details_response.raise_for_status()
            details_data = details_response.json()
            return config["parser"](details_data)

        # Single-step APIs like Zillow
        payload = config["payload"](property_info)
        response = requests.get(
            config["url"],
            headers=payload["headers"],
            params=payload.get("params", {}),
            timeout=10
        )
        response.raise_for_status()
        return config["parser"](response.json())

    except Exception as e:
        return {"service": service, "error": str(e)}

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)

        # Extract and parse property data
        text_data = extract_text(file_path)
        properties = [{"address": line} for line in text_data.splitlines() if line.strip()]

        # Fetch property data individually for each API
        results = []
        for property_info in properties:
            property_results = {"address": property_info["address"]}
            for service, config in APIS.items():
                property_results[service] = fetch_property_data(service, config, property_info)
            results.append(property_results)

        return render_template('table.html', data=results)

    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True)
