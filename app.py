from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, jsonify
import mysql.connector
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
import os
import pdfkit

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configure PDFKit
PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf="C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe")

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='12345678',
        database='verifier'
    )
# root path renders this template
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, password FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name'] 

            return redirect(url_for('dashboard'))

        return "Invalid credentials"

    return render_template('login.html')


@app.route('/register', methods=['POST', 'GET'])
def register():
    if request.method == 'GET':  
        return render_template('register.html')  # Load register page

    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')

    if not name or not email or not password:
        return jsonify({'error': 'All fields are required'}), 400

    password_hashed = generate_password_hash(password)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if email already exists
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    existing_user = cursor.fetchone()

    if existing_user:
        return jsonify({'error': 'Email already registered. Please log in.'}), 400

    # Insert new user
    cursor.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)", 
                   (name, email, password_hashed))
    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({'success': 'Registration successful! Please log in.'})  # Returning JSON instead of redirecting



@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM certificates WHERE user_id = %s", (session['user_id'],))
    certificates = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('dashboard.html', certificates=certificates, user_name=session.get('user_name'))

def generate_unique_cert_id():
    """Generate a unique certificate ID that does not exist in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    while True:
        certificate_id = str(uuid.uuid4())[:8]  # Generate 8-character unique ID
        cursor.execute("SELECT COUNT(*) FROM certificates WHERE cert_id = %s", (certificate_id,))
        result = cursor.fetchone()

        if result[0] == 0:  # If count is 0, the cert_id is unique
            break

    cursor.close()
    conn.close()
    return certificate_id

@app.route('/issue_certificate', methods=['GET', 'POST'])
def issue_certificate():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        recipient = request.form['recipient']
        cause = request.form['cause']
        certificate_id = generate_unique_cert_id()
        certificate_of = request.form['certificate_of']

        conn = get_db_connection()
        cursor = conn.cursor(prepared=True)
        cursor.execute("INSERT INTO certificates (user_id, recipient, cert_id, cause, certificate_of) VALUES (%s, %s, %s, %s, %s)",
                       (session['user_id'], recipient, certificate_id, cause, certificate_of))
        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('dashboard'))
    return render_template('issue_certificate.html')

@app.route('/verify_certificate', methods=['GET', 'POST'])
def verify_certificate():
    cert_data = None
    error = None  

    if request.method == 'POST':
        cert_id = request.form.get('cert_id', '').strip()

        if not cert_id:  # If the user submits an empty form
            error = "Please enter a Certificate ID!"
        else:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True,prepared=True)
            cursor.execute("SELECT * FROM certificates WHERE cert_id = %s", (cert_id,))
            cert_data = cursor.fetchone()
            cursor.close()
            conn.close()

    return render_template('verify_certificate.html', cert_data=cert_data, error=error)



@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

# Create a directory to save certificates temporarily
UPLOAD_FOLDER = 'static/certificates'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def generate_certificate_pdf(cert_id, recipient, cause, date, certificate_of):
    """Generate a clean PDF without extra whitespace and duplicated text"""
    
    # Ensure data is passed correctly
    recipient = recipient.strip()  # Remove extra spaces
    cause = cause.strip()
    certificate_of = certificate_of.strip()
    
    html_content = render_template(
        'certificate_template.html', 
        cert_id=cert_id, 
        recipient=recipient, 
        cause=cause,
        date=date,
        certificate_of=certificate_of
    )

    pdf_filename = f"{cert_id}.pdf"
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)

    options = {
        'page-width': '800px',
        'page-height': '600px',
        'margin-top': '0mm',
        'margin-right': '0mm',
        'margin-bottom': '0mm',
        'margin-left': '0mm',
        '--no-pdf-compression': '',  # Prevents layout shifts
        'encoding': 'UTF-8'
    }

    pdfkit.from_string(html_content, pdf_path, options=options, configuration=PDFKIT_CONFIG)
    return pdf_filename


@app.route('/download_certificate/<cert_id>', methods=['GET'])
def download_certificate(cert_id):
    # Retrieve the certificate from the database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM certificates WHERE cert_id = %s", (cert_id,))
    cert_data = cursor.fetchone()
    cursor.close()
    conn.close()

    if cert_data:
        pdf_filename = generate_certificate_pdf(cert_data['cert_id'], cert_data['recipient'], cert_data['cause'], cert_data['date'], cert_data['certificate_of'])
        # Serve the PDF file for download
        return send_file(os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename), as_attachment=True)
    return "Certificate not found", 404

if __name__ == '__main__':
    app.run(debug=True)
