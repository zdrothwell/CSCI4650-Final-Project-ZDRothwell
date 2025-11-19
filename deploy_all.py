import boto3
import time
import json
import os
import uuid
import botocore

# Ensure config directory exists
os.makedirs("../config", exist_ok=True)

REGION = "us-east-1"

# -------------------------
# 1. Create S3 bucket
# -------------------------
def create_s3_bucket(prefix="cloudgallery-images"):
    s3 = boto3.client("s3", region_name=REGION)
    bucket_name = f"{prefix}-{uuid.uuid4().hex[:8]}"

    try:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": REGION}
        )
        print(f"[S3] Bucket created: {bucket_name}")
        return bucket_name
    except botocore.exceptions.ClientError as e:
        print("[S3] Error:", e)
        return None

# -------------------------
# 2. Create Cognito User Pool + App Client
# -------------------------
def create_cognito_user_pool(pool_name="CloudGalleryUsers"):
    cognito = boto3.client("cognito-idp", region_name=REGION)

    # Create User Pool
    pool = cognito.create_user_pool(
        PoolName=pool_name,
        AutoVerifiedAttributes=["email"]
    )
    user_pool_id = pool["UserPool"]["Id"]
    print(f"[Cognito] User Pool ID: {user_pool_id}")

    # Create App Client
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

# -------------------------
# 3. Create RDS MySQL instance
# -------------------------
def create_rds_instance(db_id="cloudgallery-db",
                        username="admin",
                        password="CloudGallery123!",
                        db_name="cloudgallery"):
    ec2 = boto3.client("ec2", region_name=REGION)
    rds = boto3.client("rds", region_name=REGION)

    # Create security group
    sg = ec2.create_security_group(
        GroupName=f"{db_id}-sg",
        Description="Allow EC2 to access RDS"
    )
    sg_id = sg["GroupId"]

    # Allow inbound MySQL from anywhere (demo only)
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpProtocol="tcp",
        FromPort=3306,
        ToPort=3306,
        CidrIp="0.0.0.0/0"
    )
    print(f"[RDS] Security Group created: {sg_id}")

    # Create DB instance
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
    print("[RDS] Creating RDS instance... this may take several minutes")

    # Wait until available
    while True:
        instance = rds.describe_db_instances(DBInstanceIdentifier=db_id)
        status = instance["DBInstances"][0]["DBInstanceStatus"]
        print(f"[RDS] Current status: {status}")
        if status == "available":
            endpoint = instance["DBInstances"][0]["Endpoint"]["Address"]
            print(f"[RDS] Available! Endpoint: {endpoint}")
            return endpoint, username, password, db_name
        time.sleep(20)

# -------------------------
# 4. Write config files
# -------------------------
def write_config_files(s3_bucket, user_pool_id, client_id, rds_info):
    aws_config = {
        "region": REGION,
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

    with open("../config/aws_config.json", "w") as f:
        json.dump(aws_config, f, indent=4)
    with open("../config/db_config.json", "w") as f:
        json.dump(db_config, f, indent=4)

    print("[CONFIG] Config files created at ../config/aws_config.json and ../config/db_config.json")

# -------------------------
# MAIN DEPLOY FUNCTION
# -------------------------
def main():
    print("=== DEPLOYING CLOUDGALLERY INFRASTRUCTURE ===")
    
    s3_bucket = create_s3_bucket()
    user_pool_id, client_id = create_cognito_user_pool()
    rds_info = create_rds_instance()
    write_config_files(s3_bucket, user_pool_id, client_id, rds_info)

    print("\n=== DEPLOYMENT COMPLETE ===")
    print("Your app config files are ready in ../config/")

if __name__ == "__main__":
    main()
