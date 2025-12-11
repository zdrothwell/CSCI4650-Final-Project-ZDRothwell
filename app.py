import os
import uuid
import json
from urllib.parse import quote
from flask import Flask, render_template, request, redirect, session, url_for, flash
import boto3
import mysql.connector
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

# Prefer generated ./config/*.json when present to populate env vars used by the app.
config_db_path = "./config/db_config.json"
config_aws_path = "./config/aws_config.json"
try:
    if os.path.exists(config_db_path):
        with open(config_db_path, "r", encoding="utf-8") as f:
            dbconf = json.load(f)
        os.environ.setdefault("RDS_HOST", str(dbconf.get("db_host", "")))
        os.environ.setdefault("RDS_USER", str(dbconf.get("db_user", "")))
        os.environ.setdefault("RDS_PASS", str(dbconf.get("db_password", "")))
        os.environ.setdefault("RDS_DB", str(dbconf.get("db_name", "")))
        print(f"[CONFIG] Loaded DB config from {os.path.abspath(config_db_path)}")
    if os.path.exists(config_aws_path):
        with open(config_aws_path, "r", encoding="utf-8") as f:
            awsconf = json.load(f)
        os.environ.setdefault("AWS_REGION", str(awsconf.get("region", "")))
        os.environ.setdefault("S3_BUCKET", str(awsconf.get("s3_bucket", "")))
        os.environ.setdefault("COGNITO_POOL_ID", str(awsconf.get("user_pool_id", "")))
        os.environ.setdefault("COGNITO_CLIENT_ID", str(awsconf.get("user_pool_client_id", "")))
        print(f"[CONFIG] Loaded AWS config from {os.path.abspath(config_aws_path)}")
except Exception as e:
    print(f"[CONFIG] Failed to load generated config files: {e}")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET") or os.urandom(24)

# ---- AWS CONFIG ----
REGION = os.environ.get("AWS_REGION")
S3_BUCKET = os.environ.get("S3_BUCKET")

# ---- RDS CONFIG ----
RDS_HOST = os.environ.get("RDS_HOST")
RDS_USER = os.environ.get("RDS_USER")
RDS_PASS = os.environ.get("RDS_PASS")
RDS_DB = os.environ.get("RDS_DB")

# ---- COGNITO CONFIG ----
COGNITO_POOL_ID = os.environ.get("COGNITO_POOL_ID")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID")

# AWS clients (create after env/config load)
s3 = boto3.client("s3", region_name=REGION) if REGION else boto3.client("s3")
cognito = boto3.client("cognito-idp", region_name=REGION) if REGION else boto3.client("cognito-idp")

# ------------------ DATABASE CONNECTION ------------------
def get_db():
    return mysql.connector.connect(
        host=RDS_HOST,
        user=RDS_USER,
        password=RDS_PASS,
        database=RDS_DB,
    )

# ------------------ ROUTES ------------------

@app.route("/")
@app.route("/index")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login_user():
    username = request.form.get("username")
    password = request.form.get("password")

    if not COGNITO_CLIENT_ID:
        app.logger.error("Missing COGNITO_CLIENT_ID - check ./config/aws_config.json or environment")
        return "Server misconfiguration: COGNITO_CLIENT_ID is not set", 500

    try:
        resp = cognito.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
        )
        session["username"] = username
        # optionally store tokens if needed:
        session["id_token"] = resp.get("AuthenticationResult", {}).get("IdToken")
        return redirect(url_for("gallery"))
    except ClientError as e:
        app.logger.warning(f"Cognito login failed for {username}: {e}")
        flash("Login failed. Check your username/password.", "danger")
        return redirect(url_for("login_page"))

@app.route("/signup", methods=["GET", "POST"])
def signup_user():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("signup.html")

        try:
            # Create the user in Cognito WITHOUT an email attribute so arbitrary usernames are allowed.
            cognito.sign_up(
                ClientId=COGNITO_CLIENT_ID,
                Username=username,
                Password=password
            )

            # Auto-confirm the user so they can log in immediately (DEV/testing)
            try:
                if COGNITO_POOL_ID:
                    cognito.admin_confirm_sign_up(
                        UserPoolId=COGNITO_POOL_ID,
                        Username=username
                    )
                    app.logger.info(f"[Cognito] Auto-confirmed user {username}")
                else:
                    app.logger.warning("[Cognito] COGNITO_POOL_ID not set; skipping admin_confirm_sign_up")
            except ClientError as e:
                app.logger.warning(f"[Cognito] admin_confirm_sign_up failed for {username}: {e}")

            # Attempt to sign in immediately
            try:
                auth_resp = cognito.initiate_auth(
                    ClientId=COGNITO_CLIENT_ID,
                    AuthFlow="USER_PASSWORD_AUTH",
                    AuthParameters={"USERNAME": username, "PASSWORD": password}
                )
                session["username"] = username
                session["id_token"] = auth_resp.get("AuthenticationResult", {}).get("IdToken")
                flash("Signup successful. You are now logged in.", "success")
                return redirect(url_for("gallery"))
            except ClientError as e:
                app.logger.warning(f"[Cognito] initiate_auth after sign_up failed: {e}")
                flash("Signup succeeded but automatic login failed. Please log in.", "warning")
                return redirect(url_for("login_page"))

        except ClientError as e:
            app.logger.error(f"Signup failed for {username}: {e}")
            flash(f"Signup failed: {e.response.get('Error', {}).get('Message', str(e))}", "danger")
            return render_template("signup.html")

    return render_template("signup.html")

@app.route("/upload", methods=["GET"])
def upload_page():
    if "username" not in session:
        return redirect(url_for("login_page"))
    return render_template("upload.html")

@app.route("/upload", methods=["POST"])
def upload_image():
    if "username" not in session:
        return redirect("/login")

    file = request.files["file"]
    title = request.form["title"]
    desc = request.form["description"]
    username = session["username"]

    unique_name = f"{uuid.uuid4()}_{file.filename}"
    s3.upload_fileobj(file, S3_BUCKET, unique_name)
    file_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{unique_name}"

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO images (user_email, image_url, title, description) 
        VALUES (%s, %s, %s, %s)
        """,
        (username, file_url, title, desc),
    )
    db.commit()
    cursor.close()
    db.close()

    return redirect("/gallery")

@app.route("/gallery")
def gallery():
    if "username" not in session:
        return redirect(url_for("login_page"))

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM images ORDER BY upload_date DESC")
    images = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template("gallery.html", images=images)

# Start app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)