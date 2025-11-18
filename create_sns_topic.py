from supplychainlib.aws_sns import SNSManager

def main():
    sns = SNSManager(region_name="us-east-1")
    arn = sns.create_topic("CustomerNotifications")
    print("Created SNS Topic ARN:", arn)

if __name__ == "__main__":
    main()