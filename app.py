from flask import Flask, render_template, request, redirect, url_for, session, send_file
import mysql.connector
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
import os
import pdfkit

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configure PDFKit for Windows users (Update path if needed)
PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf="C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe")

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='12345678',
        database='verifier'
    )

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
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            return redirect(url_for('dashboard'))
        return "Invalid credentials"
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)", (name, email, password))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

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
    return render_template('dashboard.html', certificates=certificates)

@app.route('/issue_certificate', methods=['GET', 'POST'])
def issue_certificate():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        recipient = request.form['recipient']
        cause = request.form['cause']
        certificate_id = str(uuid.uuid4())[:8]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO certificates (user_id, recipient, cert_id, cause) VALUES (%s, %s, %s, %s)",
                       (session['user_id'], recipient, certificate_id, cause))
        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('dashboard'))
    return render_template('issue_certificate.html')

@app.route('/verify_certificate', methods=['GET', 'POST'])
def verify_certificate():
    cert_data = None
    if request.method == 'POST':
        cert_id = request.form['cert_id']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM certificates WHERE cert_id = %s", (cert_id,))
        cert_data = cursor.fetchone()
        cursor.close()
        conn.close()
    return render_template('verify_certificate.html', cert_data=cert_data)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

# Create a directory to save certificates temporarily
UPLOAD_FOLDER = 'static/certificates'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def generate_certificate_pdf(cert_id, recipient, cause):
    """ Generates a PDF from an HTML template using pdfkit """
    html_content = render_template('certificate_template.html', cert_id=cert_id, recipient=recipient, cause=cause)
    
    pdf_filename = f"{cert_id}.pdf"
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)
    
    # Convert HTML to PDF
    pdfkit.from_string(html_content, pdf_path, configuration=PDFKIT_CONFIG)  # Windows users: add PDFKIT_CONFIG
    
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
        pdf_filename = generate_certificate_pdf(cert_data['cert_id'], cert_data['recipient'], cert_data['cause'])
        # Serve the PDF file for download
        return send_file(os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename), as_attachment=True)
    return "Certificate not found", 404

if __name__ == '__main__':
    app.run(debug=True)
