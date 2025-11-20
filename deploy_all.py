import boto3
import time
import json
import os
import uuid
import botocore
import mysql.connector
from mysql.connector import Error as MySQLError

# -------------------------
# CONFIG
# -------------------------
region = "us-east-1"
os.makedirs("./config", exist_ok=True)

# -------------------------
# 1. Create S3 Bucket
# -------------------------
def create_s3_bucket(bucket_name):
    s3 = boto3.client("s3", region_name=region)
    try:
        if region == "us-east-1":
            # us-east-1 cannot have LocationConstraint
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region}
            )
        print(f"[S3] Bucket created: {bucket_name}")
        return bucket_name
    except Exception as e:
        print(f"[S3] Error creating bucket: {e}")
        return None

# -------------------------
# 2. Create Cognito User Pool + App Client
# -------------------------
def create_cognito_user_pool(pool_name="CloudGalleryUsers"):
    cognito = boto3.client("cognito-idp", region_name=region)
    try:
        # Create user pool
        pool = cognito.create_user_pool(
            PoolName=pool_name,
            AutoVerifiedAttributes=[]
        )
        user_pool_id = pool["UserPool"]["Id"]
        print(f"[Cognito] User Pool ID: {user_pool_id}")

        # Create App client
        client = cognito.create_user_pool_client(
            UserPoolId=user_pool_id,
            ClientName="CloudGalleryAppClient",
            GenerateSecret=False,
            ExplicitAuthFlows=[
                "ALLOW_USER_PASSWORD_AUTH",
                "ALLOW_REFRESH_TOKEN_AUTH",
                "ALLOW_USER_SRP_AUTH"
            ]
        )
        client_id = client["UserPoolClient"]["ClientId"]
        print(f"[Cognito] App Client ID: {client_id}")

        return user_pool_id, client_id
    except Exception as e:
        print(f"[Cognito] Error: {e}")
        return None, None

# -------------------------
# 3. Create RDS Instance
# -------------------------
def create_rds_instance(db_id="cloudgallery-db",
                        username="admin",
                        password="CloudGallery123!",
                        db_name="cloudgallery",
                        wait_timeout=900,
                        poll_interval=15):
    ec2 = boto3.client("ec2", region_name=region)
    rds = boto3.client("rds", region_name=region)
    try:
        # Create security group
        sg = ec2.create_security_group(
            GroupName=f"{db_id}-sg",
            Description="Allow EC2 to access RDS"
        )
        sg_id = sg["GroupId"]

        # Allow inbound MySQL (demo only)
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol="tcp",
            FromPort=3306,
            ToPort=3306,
            CidrIp="0.0.0.0/0"
        )
        print(f"[RDS] Security Group created: {sg_id}")

        # Create DB instance (may raise if instance already exists)
        try:
            rds.create_db_instance(
                DBName=db_name,
                DBInstanceIdentifier=db_id,
                AllocatedStorage=20,
                DBInstanceClass="db.t3.micro",
                Engine="mysql",
                MasterUsername=username,
                MasterUserPassword=password,
                VpcSecurityGroupIds=[sg_id],
                PubliclyAccessible=True
            )
            print("[RDS] DB instance creation started (may take several minutes)")
        except botocore.exceptions.ClientError as e:
            # If instance already exists, continue to poll for endpoint
            code = e.response.get("Error", {}).get("Code", "")
            if code == "DBInstanceAlreadyExists":
                print("[RDS] DB instance already exists, attempting to discover endpoint")
            else:
                raise

        # Poll until instance is available or timeout
        start = time.time()
        while True:
            try:
                resp = rds.describe_db_instances(DBInstanceIdentifier=db_id)
                inst = resp["DBInstances"][0]
                status = inst.get("DBInstanceStatus")
                print(f"[RDS] status={status}")
                if status == "available" and "Endpoint" in inst and "Address" in inst["Endpoint"]:
                    endpoint = inst["Endpoint"]["Address"]
                    print(f"[RDS] Endpoint available: {endpoint}")
                    return endpoint, username, password, db_name
            except botocore.exceptions.ClientError as e:
                # If not found yet, continue polling
                print(f"[RDS] describe_db_instances: {e}")
            if time.time() - start > wait_timeout:
                print("[RDS] Timeout waiting for DB to become available; returning placeholder 'pending'")
                return "pending", username, password, db_name
            time.sleep(poll_interval)

    except Exception as e:
        print(f"[RDS] Error: {e}")
        return None, username, password, db_name

# -------------------------
# NEW: run create_tables.sql once DB is ready
# -------------------------
def run_sql_file(host, user, password, db_name, sql_path="./create_tables.sql"):
    abs_sql = os.path.abspath(sql_path)
    print(f"[DB INIT] Attempting to run SQL file: {abs_sql}")
    if not os.path.exists(abs_sql):
        print(f"[DB INIT] SQL file not found at {abs_sql}, skipping DB init.")
        return False

    try:
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=db_name,
            connection_timeout=10
        )
        cursor = conn.cursor()
        with open(abs_sql, "r", encoding="utf-8") as f:
            sql = f.read()
        # Split on semicolon and execute statements that are not empty
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            try:
                cursor.execute(stmt)
            except MySQLError as e:
                print(f"[DB INIT] Error executing statement: {e}; statement snippet: {stmt[:80]}")
        conn.commit()
        cursor.close()
        conn.close()
        print("[DB INIT] create_tables.sql executed successfully.")
        return True
    except Exception as e:
        print(f"[DB INIT] Failed to run SQL file: {e}")
        return False

# -------------------------
# 4. Write Config Files (improved logging + abs paths)
# -------------------------
def write_config_files(s3_bucket, user_pool_id, client_id, rds_info):
    aws_config = {
        "region": region,
        "s3_bucket": s3_bucket,
        "user_pool_id": user_pool_id,
        "user_pool_client_id": client_id,
        "cloudfront_domain": "",
        "cognito_domain_prefix": "",
        "identity_pool_id": ""
    }

    db_config = {
        "db_host": rds_info[0],
        "db_user": rds_info[1],
        "db_password": rds_info[2],
        "db_name": rds_info[3],
        "db_port": 3306
    }

    aws_path = "./config/aws_config.json"
    db_path = "./config/db_config.json"
    with open(aws_path, "w", encoding="utf-8") as f:
        json.dump(aws_config, f, indent=4)
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db_config, f, indent=4)

    print(f"[CONFIG] Config files created:")
    print(f"  - {os.path.abspath(aws_path)}")
    print(f"  - {os.path.abspath(db_path)}")

# -------------------------
# 5. Main Deploy Function (now runs DB init when endpoint available)
# -------------------------
def main():
    print("=== DEPLOYING CLOUDGALLERY INFRASTRUCTURE ===")

    # Generate unique bucket name
    bucket_name = "cloudgallery-" + str(uuid.uuid4())[:8]
    s3_bucket = create_s3_bucket(bucket_name)

    user_pool_id, client_id = create_cognito_user_pool()
    rds_info = create_rds_instance()

    write_config_files(s3_bucket, user_pool_id, client_id, rds_info)

    # If we have a real RDS endpoint, attempt to run create_tables.sql
    db_host = rds_info[0]
    if db_host and db_host != "pending" and db_host != "None":
        print(f"[MAIN] Detected RDS host: {db_host} — attempting to initialize schema.")
        ok = run_sql_file(db_host, rds_info[1], rds_info[2], rds_info[3], sql_path="./create_tables.sql")
        if not ok:
            print("[MAIN] DB init failed or was skipped. You may need to run create_tables.sql manually once DB is reachable.")
    else:
        print("[MAIN] RDS endpoint not ready (pending). Skipping DB initialization. Re-run DB init after endpoint is available.")

    print("\n=== DEPLOYMENT COMPLETE ===")
    print("Your app config files are ready in ./config/")
    print("RDS endpoint may still be pending. Run a separate script to check once available.")

# -------------------------
if __name__ == "__main__":
    main()
