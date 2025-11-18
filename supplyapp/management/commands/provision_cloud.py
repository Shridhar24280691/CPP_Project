from django.core.management.base import BaseCommand
import boto3
from botocore.exceptions import ClientError


class DynamoProvisioner:
    """Creates required DynamoDB tables automatically if they do not exist."""

    def __init__(self, region='us-east-1'):
        self.dynamodb = boto3.client('dynamodb', region_name=region)
        self.region = region

    def table_exists(self, table_name):
        try:
            existing = self.dynamodb.list_tables()['TableNames']
            return table_name in existing
        except ClientError as e:
            print(f"Error listing tables: {e}")
            return False

    def create_table(self, name, key_name):
        """Create a DynamoDB table with PAY_PER_REQUEST billing."""
        try:
            self.dynamodb.create_table(
                TableName=name,
                KeySchema=[{"AttributeName": key_name, "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": key_name, "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST"
            )
            print(f"Table '{name}' created successfully.")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceInUseException':
                print(f"Table '{name}' already exists.")
            else:
                print(f"Error creating table {name}: {e}")

    def provision_all(self):
        """Create all required tables for the Gourmet Coffee system."""
        tables = {
            "Suppliers": "id",
            "RawMaterials": "id",
            "FinishedProducts": "finished_id",
            "Distributors": "id",
            "DistributorOrders": "order_id",
            "DistributorInventory": "id",
            "CustomerOrders": "order_id",
        }

        for name, key in tables.items():
            if not self.table_exists(name):
                print(f"Creating DynamoDB table: {name}")
                self.create_table(name, key)
            else:
                print(f"Table '{name}' already exists, skipping.")


class Command(BaseCommand):
    help = "Provision all DynamoDB tables for the Gourmet Coffee Supply Chain system."

    def handle(self, *args, **options):
        region = 'us-east-1'
        print("Starting AWS DynamoDB table provisioning...")

        provisioner = DynamoProvisioner(region)
        provisioner.provision_all()

        print("All tables verified or created successfully.")
