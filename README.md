# CSCI4650 Final Project Dynamic Photo Hosting Website 
 Final Project for Intro to Cloud Computing course with an AWS website deployment package for a photo hosting website

## Getting Started
The first things you will need to ensure you have setup are an IAM profile with an Access Key and Secret Key, and a VPC with at least two subnets routed into an internet gateway to create the availability zone for the RDS database that will be deployed later on.

This is what the VPC Resource Map should look like to get started:

![alt text](image.png)


## Starting an EC2 Instance
Now that we have our VPC up and ready to go, this is where get started by deploying an EC2 instance in whatever region you choose. If you decide to use a region that is not us-east-2, make sure you change the variable in the deploy_all.py file once you are in the EC2 instance using whatever file editor you wish.

Start by going to the EC2 page on AWS. Click "Launch Instance" and go ahead and name it whatever you wish. Select a Key Pair or generate a new one if you need to do so, then click "Edit" in the Network Settings section. You will need to create two new Inbound Rules. One for port 80 (HTTP) and one for port 5000. The source can be anywhere or just your device if you are the only person connecting to it.

Once you have the Inbound Rules for the Security Group set, go ahead and click "Launch Instance". 

After it has launched, click its name in the Instances list and click "Connect". Using EC2 Instance Connect, go ahead and hit the orange "Connect" button at the bottom right. Once you are in the terminal, set up the EC2 instance by running these commands:

```aws configure```
    - This is where you will need the Access Key, Secret Key, and Region you defined/chose earlier. The fourth setting just leave blank and hit enter.

```
sudo dnf install python3-pip git -y
git clone https://github.com/zdrothwell/CSCI4650-Final-Project-ZDRothwell.git website
cd website
pip3 install -r requirements.txt
python3 deploy_all.py
```