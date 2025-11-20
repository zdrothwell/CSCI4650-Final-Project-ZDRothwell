import os
import uuid
from flask import Flask, render_template, request, redirect, session
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
    if os.path.exists(config_aws_path):
        with open(config_aws_path, "r", encoding="utf-8") as f:
            awsconf = json.load(f)
        os.environ.setdefault("AWS_REGION", str(awsconf.get("region", "")))
        os.environ.setdefault("S3_BUCKET", str(awsconf.get("s3_bucket", "")))
except Exception as e:
    print(f"[CONFIG] Failed to load generated config files: {e}")


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET") or os.environ.get("SESSION_SECRET") or os.urandom(24)

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

# AWS clients
s3 = boto3.client("s3", region_name=REGION)
cognito = boto3.client("cognito-idp", region_name=REGION)

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
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login_user():
    username = request.form["username"]
    password = request.form["password"]

    try:
        resp = cognito.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
        )
        session["username"] = username
        return redirect("/gallery")
    except ClientError:
        return "Login failed. Check your username/password."

@app.route("/signup", methods=["GET", "POST"])
def signup_user():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        try:
            cognito.sign_up(
                ClientId=COGNITO_CLIENT_ID,
                Username=username,
                Password=password
            )
            return redirect("/login")
        except ClientError as e:
            return f"Signup failed: {str(e)}"

    return render_template("signup.html")

@app.route("/upload", methods=["GET"])
def upload_page():
    if "username" not in session:
        return redirect("/login")
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
        return redirect("/login")

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
