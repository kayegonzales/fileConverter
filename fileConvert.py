from flask import Flask, request, jsonify, render_template, redirect, url_for
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
TEMPLATE_FOLDER = 'templates'  # Default Flask folder for templates

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variable to store processed data temporarily
global combined_data_global
combined_data_global = []

# Define path to Tesseract executable
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# Route for the homepage, rendering index.html
@app.route('/')
def index():
    return render_template('index.html')

# Function to process and extract data from different file types
def extract_data(file_path, file_type):
    try:
        if file_type == 'csv':
            # Detect encoding for robust CSV handling using charset-normalizer
            with open(file_path, 'rb') as raw_file:
                result = from_bytes(raw_file.read()).best()
                encoding = result.encoding
            df = pd.read_csv(file_path, encoding=encoding)
            df = df.replace({np.nan: None})  # Replace NaN with None for JSON serialization
            return df.to_dict(orient='records')

        elif file_type == 'xlsx':
            # Process Excel files
            df = pd.read_excel(file_path, engine='openpyxl')
            df = df.replace({np.nan: None})
            return df.to_dict(orient='records')

        elif file_type == 'pdf':
            # Extract text from PDFs
            pdf_reader = PyPDF2.PdfReader(file_path)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text

        elif file_type in ['jpeg', 'jpg', 'png']:
            # Extract text from images using Tesseract
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image)
            return text

        elif file_type in ['txt']:
            # Read plain text files
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
            return text

        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    except Exception as e:
        logger.error(f"Error processing file of type {file_type}: {e}")
        raise

# Function to split text into manageable chunks for Make.com
def split_text_for_make(text, max_chunk_size=3000):
    """
    Splits the text into manageable chunks for Make.com.
    Args:
        text (str): The raw extracted text.
        max_chunk_size (int): The maximum size of each chunk in characters.
    Returns:
        list: A list of text chunks.
    """
    words = text.split()
    chunks = []
    current_chunk = []

    for word in words:
        if len(' '.join(current_chunk) + ' ' + word) <= max_chunk_size:
            current_chunk.append(word)
        else:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return chunks

# Route for file upload and processing
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Save and process the file
    if file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)

        # Determine the file type
        file_type = file.filename.rsplit('.', 1)[1].lower()

        try:
            # Extract data based on file type
            raw_data = extract_data(file_path, file_type)

            if isinstance(raw_data, str):
                # Split text data into chunks
                chunks = split_text_for_make(raw_data, max_chunk_size=3000)
                payload = {'chunks': chunks}
            elif isinstance(raw_data, list):
                # For structured data like CSV/Excel
                payload = {'data': raw_data}
            else:
                raise ValueError("Unsupported data format")

            # Send payload to Make.com
            webhook_url = "https://hook.us1.make.com/huolkx7l5lpug0q51wxftsvfctnkcday"
            headers = {'Content-Type': 'application/json'}
            response = requests.post(webhook_url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Data successfully sent to Make.com: {response.status_code}")
            return jsonify({'status': 'success', 'message': 'Data sent to Make.com'}), 200

        except Exception as e:
            logger.error(f"Error processing file: {e}")
            return jsonify({'error': f'Failed to process file: {str(e)}'}), 500

# Route to display processed data (if needed)
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
    port = int(os.environ.get('PORT', 5000))  # Get the PORT from Heroku's environment
    logger.info(f"Starting server on port {port}")
    app.run(debug=False, host='0.0.0.0', port=port)
