from flask import Flask, request, jsonify, render_template
import os
import requests
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
UPLOAD_FOLDER = './uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Define API endpoints and their specific payload structures and response parsers
APIS = {
    "Zillow": {
        "url": "https://api.zillow.com/property",
        "payload": lambda property_info: {
            "address": property_info["address"],
            "zip": property_info.get("zip", "")
        },
        "parser": lambda response: {
            "price": response.get("estimated_price", "N/A"),
            "status": response.get("status", "Unknown")
        }
    },
    "Movoto": {
        "url": "https://api.movoto.com/property",
        "payload": lambda property_info: {
            "location": property_info["address"],
            "state": property_info.get("state", "")
        },
        "parser": lambda response: {
            "price": response.get("price_estimate", "N/A"),
            "availability": response.get("listing_status", "Unknown")
        }
    },
    "Redfin": {
        "url": "https://api.redfin.com/property",
        "payload": lambda property_info: {
            "query": property_info["address"],
            "city": property_info.get("city", "")
        },
        "parser": lambda response: {
            "price": response.get("value", "N/A"),
            "for_sale": response.get("for_sale", False)
        }
    }
}

# Function to extract text from uploaded file
def extract_text(file_path):
    # Add file type handling (e.g., PDF, DOCX) here
    with open(file_path, 'r') as file:
        return file.read()

# Function to make API call with specific payload and parse the response
def fetch_property_data(service, config, property_info):
    try:
        payload = config["payload"](property_info)
        response = requests.post(config["url"], json=payload, timeout=10)
        response.raise_for_status()
        parsed_data = config["parser"](response.json())
        return {"service": service, "data": parsed_data}
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
        
        # Extract text from the file
        text_data = extract_text(file_path)
        # Convert text into structured property data (mockup example)
        properties = [{"address": line} for line in text_data.splitlines() if line.strip()]

        # Fetch property data in parallel
        with ThreadPoolExecutor() as executor:
            results = list(executor.map(
                lambda property_info: {
                    "property": property_info,
                    "estimates": [
                        fetch_property_data(service, config, property_info)
                        for service, config in APIS.items()
                    ]
                },
                properties
            ))

        # Consolidate and prepare the response
        consolidated_data = [
            {
                "property": result["property"],
                "estimates": result["estimates"]
            }
            for result in results
        ]

        return render_template('results.html', data=consolidated_data)

    return render_template('upload.html')

@app.route('/results', methods=['POST'])
def display_results():
    data = request.json
    return jsonify({"results": data})

if __name__ == '__main__':
    app.run(debug=True)