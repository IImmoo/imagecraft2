import os
from flask import Flask, request, jsonify, send_file, redirect, render_template, url_for
from werkzeug.utils import secure_filename
import cv2
import numpy as np
from rembg import remove
from PIL import Image
import io
import shopify
from dotenv import load_dotenv
from flask_cors import CORS
import requests
import hmac
import hashlib
import base64
import json

load_dotenv()

app = Flask(__name__)
CORS(app)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PROCESSED_FOLDER'] = 'processed'

# Shopify API kimlik bilgileri
SHOPIFY_API_KEY = os.getenv('SHOPIFY_API_KEY')
SHOPIFY_API_SECRET = os.getenv('SHOPIFY_API_SECRET')
SHOPIFY_SCOPE = 'write_products,write_files'
APP_URL = 'https://imagecraft-6430.onrender.com'

# Klasörleri oluştur
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)

def verify_webhook(data, hmac_header):
    digest = hmac.new(SHOPIFY_API_SECRET.encode('utf-8'), data, hashlib.sha256).digest()
    computed_hmac = base64.b64encode(digest).decode('utf-8')
    return hmac.compare_digest(computed_hmac, hmac_header)

@app.route('/')
def index():
    """Ana sayfa"""
    shop = request.args.get('shop')
    if shop:
        return install(shop)
    return render_template('index.html')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def process_image(image_path):
    try:
        # Görüntüyü yükle
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError("Image could not be loaded")
        
        # Logo kaldırma işlemi
        output = remove(img)
        
        # Alfa kanalını kaldır ve beyaz arka plan ekle
        if output.shape[2] == 4:  # RGBA format
            alpha = output[:, :, 3] / 255.0
            output_rgb = output[:, :, :3]
            white_bg = np.ones_like(output_rgb) * 255
            output_final = (alpha[:, :, np.newaxis] * output_rgb + 
                          (1 - alpha[:, :, np.newaxis]) * white_bg).astype(np.uint8)
        else:
            output_final = output
        
        return output_final
    except Exception as e:
        app.logger.error(f"Error processing image: {str(e)}")
        raise

def verify_request():
    # HMAC doğrulaması
    query_dict = dict(request.args)
    if 'hmac' not in query_dict:
        return False
    
    hmac_value = query_dict.pop('hmac')
    sorted_params = '&'.join([f"{key}={value}" for key, value in sorted(query_dict.items())])
    
    digest = hmac.new(
        SHOPIFY_API_SECRET.encode('utf-8'),
        sorted_params.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(digest, hmac_value)

@app.route('/install')
def install(shop_url=None):
    """Shopify uygulaması kurulum endpoint'i"""
    if not shop_url:
        shop_url = request.args.get('shop')
    if not shop_url:
        return 'Shop parameter is required', 400
    
    state = base64.b64encode(os.urandom(16)).decode('utf-8')
    redirect_uri = f"{APP_URL}/oauth/callback"
    
    # Shopify OAuth URL'sini oluştur
    install_url = f"https://{shop_url}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}&scope={SHOPIFY_SCOPE}&redirect_uri={redirect_uri}&state={state}"
    
    return redirect(install_url)

@app.route('/oauth/callback')
def oauth_callback():
    """Shopify OAuth callback endpoint'i"""
    # HMAC doğrulaması
    if not verify_request():
        return 'Invalid signature', 400
    
    shop_url = request.args.get('shop')
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not shop_url or not code:
        return 'Missing required parameters', 400
    
    try:
        # Access token'ı al
        access_token_url = f"https://{shop_url}/admin/oauth/access_token"
        response = requests.post(access_token_url, data={
            'client_id': SHOPIFY_API_KEY,
            'client_secret': SHOPIFY_API_SECRET,
            'code': code
        })
        
        if response.ok:
            # Token'ı kaydet ve kullanıcıyı uygulamaya yönlendir
            data = response.json()
            access_token = data.get('access_token')
            
            # Burada token'ı güvenli bir şekilde saklamalısınız
            
            # Kullanıcıyı uygulamaya yönlendir
            app_url = f"https://{shop_url}/admin/apps/imagecraft"
            return redirect(app_url)
        else:
            return 'Installation failed: ' + response.text, 400
            
    except Exception as e:
        app.logger.error(f"OAuth error: {str(e)}")
        return f'Installation failed: {str(e)}', 400

@app.route('/process', methods=['POST'])
def process():
    """Görüntü işleme endpoint'i"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    
    try:
        # Dosyayı kaydet
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)
        
        # Görüntüyü işle
        processed_image = process_image(input_path)
        
        # İşlenmiş görüntüyü kaydet
        output_filename = f"processed_{filename}"
        output_path = os.path.join(app.config['PROCESSED_FOLDER'], output_filename)
        cv2.imwrite(output_path, processed_image)
        
        # İşlenmiş görüntüyü döndür
        return send_file(output_path, mimetype='image/png')
        
    except Exception as e:
        app.logger.error(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
    finally:
        # Geçici dosyaları temizle
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 