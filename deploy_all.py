import boto3
import time
import json
import os
import uuid
import botocore

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
                        db_name="cloudgallery"):
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
        print("[RDS] DB instance creation started (may take several minutes)")

        # Return info immediately
        return "pending", username, password, db_name
    except Exception as e:
        print(f"[RDS] Error: {e}")
        return None, username, password, db_name

# -------------------------
# 4. Write Config Files
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

    with open("./config/aws_config.json", "w") as f:
        json.dump(aws_config, f, indent=4)
    with open("./config/db_config.json", "w") as f:
        json.dump(db_config, f, indent=4)

    print("[CONFIG] Config files created at ./config/aws_config.json and ./config/db_config.json")

# -------------------------
# 5. Main Deploy Function
# -------------------------
def main():
    print("=== DEPLOYING CLOUDGALLERY INFRASTRUCTURE ===")

    # Generate unique bucket name
    bucket_name = "cloudgallery-" + str(uuid.uuid4())[:8]
    s3_bucket = create_s3_bucket(bucket_name)

    user_pool_id, client_id = create_cognito_user_pool()
    rds_info = create_rds_instance()

    write_config_files(s3_bucket, user_pool_id, client_id, rds_info)

    print("\n=== DEPLOYMENT COMPLETE ===")
    print("Your app config files are ready in ./config/")
    print("RDS endpoint may still be pending. Run a separate script to check once available.")

# -------------------------
if __name__ == "__main__":
    main()
