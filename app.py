import os
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import cv2
import numpy as np
from rembg import remove
from PIL import Image
import io
import shopify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PROCESSED_FOLDER'] = 'processed'

# Shopify API kimlik bilgileri
SHOPIFY_API_KEY = os.getenv('SHOPIFY_API_KEY')
SHOPIFY_API_SECRET = os.getenv('SHOPIFY_API_SECRET')
SHOPIFY_SCOPE = 'write_products,write_files'

# Klasörleri oluştur
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def process_image(image_path):
    # Görüntüyü yükle
    img = cv2.imread(image_path)
    
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

@app.route('/install')
def install():
    """Shopify uygulaması kurulum endpoint'i"""
    shop_url = request.args.get('shop')
    if not shop_url:
        return 'Shop parameter is required', 400
    
    auth_url = f"https://{shop_url}/admin/oauth/authorize"
    redirect_uri = request.url_root + 'oauth/callback'
    
    # Shopify OAuth URL'sini oluştur
    install_url = shopify.Session(shop_url, SHOPIFY_SCOPE).create_permission_url(
        scope=SHOPIFY_SCOPE,
        redirect_uri=redirect_uri
    )
    
    return redirect(install_url)

@app.route('/oauth/callback')
def oauth_callback():
    """Shopify OAuth callback endpoint'i"""
    # OAuth işlemlerini tamamla
    shop_url = request.args.get('shop')
    code = request.args.get('code')
    
    session = shopify.Session(shop_url, SHOPIFY_SCOPE)
    access_token = session.request_token(code)
    
    # Token'ı kaydet (gerçek uygulamada güvenli bir şekilde saklanmalı)
    # ...
    
    return 'Installation successful!'

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
        return jsonify({'error': str(e)}), 500
    
    finally:
        # Geçici dosyaları temizle
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)

if __name__ == '__main__':
    app.run(debug=True) 