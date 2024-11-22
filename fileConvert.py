from flask import Flask, request, jsonify, render_template
import os
import pandas as pd
from PIL import Image
import pytesseract
import PyPDF2
import numpy as np
import logging
import requests
from charset_normalizer import from_bytes

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    return render_template('index.html')  # Ensure index.html is in the templates/ folder

def extract_data(file_path, file_type):
    try:
        if file_type == 'csv':
            # Detect encoding for robust CSV handling using charset-normalizer
            with open(file_path, 'rb') as raw_file:
                result = from_bytes(raw_file.read()).best()
                encoding = result.encoding
            df = pd.read_csv(file_path, encoding=encoding)

            # Debugging: Log the structure of the CSV file
            logger.info(f"CSV Columns: {df.columns.tolist()}")
            logger.info(f"Sample Data:\n{df.head()}")

            # If there's only one column, assume it contains the full address
            if len(df.columns) == 1:
                df.rename(columns={df.columns[0]: "Address"}, inplace=True)  # Ensure column is named "Address"
            else:
                # Combine all columns into a single "Address" field for multi-column CSVs
                df['Address'] = df.apply(
                    lambda row: ', '.join(row.dropna().astype(str).str.strip()), axis=1
                )

            logger.info(f"Processed Address Data:\n{df['Address'].head()}")

            df = df.replace({np.nan: None})  # Replace NaN with None for JSON serialization
            return df[['Address']].to_dict(orient='records')  # Return only the "Address" field

        elif file_type == 'xlsx':
            df = pd.read_excel(file_path, engine='openpyxl')
            df = df.replace({np.nan: None})
            return df.to_dict(orient='records')

        elif file_type == 'pdf':
            pdf_reader = PyPDF2.PdfReader(file_path)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text

        elif file_type in ['jpeg', 'jpg', 'png']:
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image)
            return text

        elif file_type in ['txt']:
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
            return text

        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    except Exception as e:
        logger.error(f"Error processing file of type {file_type}: {e}")
        raise


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)

        file_type = file.filename.rsplit('.', 1)[1].lower()

        try:
            raw_data = extract_data(file_path, file_type)

            if isinstance(raw_data, list):
                payload = {'data': raw_data}
            else:
                raise ValueError("Unsupported data format")

            logger.info(f"Payload to webhook: {payload}")

            webhook_url = "https://hook.us1.make.com/huolkx7l5lpug0q51wxftsvfctnkcday"
            headers = {'Content-Type': 'application/json'}
            response = requests.post(webhook_url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Data successfully sent to Make.com: {response.status_code}")
            return jsonify({'status': 'success', 'message': 'Data sent to Make.com'}), 200

        except Exception as e:
            logger.error(f"Error processing file: {e}")
            return jsonify({'error': f'Failed to process file: {str(e)}'}), 500

@app.route('/webhook', methods=['POST', 'GET'])
def display_data():
    global combined_data_global
    try:
        if request.method == 'POST':
            incoming_data = request.get_json()
            if not incoming_data:
                return jsonify({'error': 'No data received'}), 400

            combined_data_global = incoming_data.get('aggregated_properties', [])
            return jsonify({'status': 'success', 'message': 'Data received and stored'}), 200

        elif request.method == 'GET':
            if not combined_data_global:
                return jsonify({'error': 'No data available'}), 400
            return jsonify({'data': combined_data_global}), 200

    except Exception as e:
        logger.error(f"Error handling webhook data: {e}")
        return jsonify({'error': 'Failed to handle data', 'details': str(e)}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))  # Use the PORT variable from the environment
    app.run(host='0.0.0.0', port=port, debug=False)  # Bind to all network interfaces and use the assigned port

