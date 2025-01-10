import os
from flask import Flask, request, jsonify, send_file, redirect, render_template, url_for, session, make_response
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
import secrets
from flask_session import Session
import logging

# Logging ayarları
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SHOPIFY_API_SECRET', 'your-secret-key')
CORS(app)

# Session ayarları
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 saat
Session(app)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PROCESSED_FOLDER'] = 'processed'

# Shopify API kimlik bilgileri
SHOPIFY_API_KEY = os.getenv('SHOPIFY_API_KEY')
SHOPIFY_API_SECRET = os.getenv('SHOPIFY_API_SECRET')
SHOPIFY_SCOPE = 'write_products,write_files'
APP_URL = 'https://imagecraft-6430.onrender.com'

# Debug modunu aktifleştir
app.debug = True

# Klasörleri oluştur
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)
os.makedirs('flask_session', exist_ok=True)  # Session dosyaları için klasör

@app.route('/debug')
def debug():
    """Debug endpoint'i"""
    try:
        response_data = {
            'session': dict(session),
            'env': {
                'SHOPIFY_API_KEY': SHOPIFY_API_KEY,
                'APP_URL': APP_URL,
                'SHOPIFY_SCOPE': SHOPIFY_SCOPE
            },
            'request': {
                'args': dict(request.args),
                'headers': dict(request.headers)
            }
        }
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Debug endpoint error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    """Ana sayfa"""
    shop = request.args.get('shop')
    if shop:
        logger.debug(f"Shop parameter received: {shop}")
        return install(shop)
    logger.debug("No shop parameter, rendering index.html")
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
    logger.debug(f"Install endpoint called with shop_url: {shop_url}")
    
    if not shop_url:
        shop_url = request.args.get('shop')
    if not shop_url:
        logger.error("No shop parameter provided")
        return 'Shop parameter is required', 400
    
    # Nonce oluştur
    nonce = secrets.token_hex(16)
    logger.debug(f"Generated nonce: {nonce}")
    
    # Session'ı temizle ve yeni değerleri kaydet
    session.clear()
    session['nonce'] = nonce
    session['shop'] = shop_url
    
    # Session'ı kaydet
    session.modified = True
    
    redirect_uri = f"{APP_URL}/oauth/callback"
    
    # Shopify OAuth URL'sini oluştur
    install_url = (
        f"https://{shop_url}/admin/oauth/authorize?"
        f"client_id={SHOPIFY_API_KEY}&"
        f"scope={SHOPIFY_SCOPE}&"
        f"redirect_uri={redirect_uri}&"
        f"state={nonce}"
    )
    
    logger.debug(f"Redirecting to Shopify OAuth URL: {install_url}")
    response = make_response(redirect(install_url))
    response.set_cookie('nonce', nonce, secure=True, httponly=True, samesite='None')
    response.set_cookie('shop', shop_url, secure=True, httponly=True, samesite='None')
    return response

@app.route('/oauth/callback')
def oauth_callback():
    """Shopify OAuth callback endpoint'i"""
    logger.debug("OAuth callback received")
    logger.debug(f"Request args: {dict(request.args)}")
    logger.debug(f"Session data: {dict(session)}")
    logger.debug(f"Cookies: {request.cookies}")
    
    # Nonce kontrolü
    state = request.args.get('state')
    nonce = request.cookies.get('nonce')
    if not state or state != nonce:
        logger.error(f"Invalid state. Received: {state}, Expected: {nonce}")
        return 'Invalid state parameter', 400
    
    shop_url = request.args.get('shop')
    stored_shop = request.cookies.get('shop')
    if shop_url != stored_shop:
        logger.error(f"Invalid shop. Received: {shop_url}, Expected: {stored_shop}")
        return 'Invalid shop parameter', 400
    
    code = request.args.get('code')
    if not code:
        logger.error("Missing code parameter")
        return 'Missing code parameter', 400
    
    try:
        # Access token'ı al
        access_token_url = f"https://{shop_url}/admin/oauth/access_token"
        response = requests.post(access_token_url, data={
            'client_id': SHOPIFY_API_KEY,
            'client_secret': SHOPIFY_API_SECRET,
            'code': code
        })
        
        logger.debug(f"Token request response: {response.text}")
        
        if response.ok:
            data = response.json()
            access_token = data.get('access_token')
            
            # Token'ı session'a kaydet
            session['access_token'] = access_token
            session.modified = True
            
            # Kullanıcıyı uygulamaya yönlendir
            app_url = f"https://{shop_url}/admin/apps/{SHOPIFY_API_KEY}"
            logger.debug(f"Redirecting to app URL: {app_url}")
            return redirect(app_url)
        else:
            logger.error(f"Token request failed: {response.text}")
            return 'Installation failed: Invalid response from Shopify', 400
            
    except Exception as e:
        logger.error(f"OAuth error: {str(e)}")
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