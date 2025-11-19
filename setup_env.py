# aws_infra/setup_env.py

def write_env_file(data):
    with open("../.env", "w") as f:
        for key, value in data.items():
            f.write(f"{key}={value}\n")

    print("[ENV] .env file created!")


if __name__ == "__main__":
    sample = {
        "S3_BUCKET": "bucket-name",
        "AWS_REGION": "us-east-1",
        "RDS_HOST": "example.us-east-1.rds.amazonaws.com",
        "RDS_USER": "admin",
        "RDS_PASS": "CloudGallery123!",
        "RDS_DB": "cloudgallery",
        "COGNITO_POOL_ID": "us-east-1_XXXX",
        "COGNITO_CLIENT_ID": "XXXX"
    }

    write_env_file(sample)
