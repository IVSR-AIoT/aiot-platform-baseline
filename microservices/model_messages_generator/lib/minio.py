import boto3
import json
from botocore.exceptions import NoCredentialsError, PartialCredentialsError


class MinioS3Client:
    def __init__(self, credential_file):
        self.credential_file = credential_file
        self.s3_client = self._initializeClient()
        print(self.s3_client.meta.events)

    def _initializeClient(self):
        """
        Initialize the S3 client with the credentials from the JSON file.
        """
        try:
            # Read credentials from the JSON file
            with open(self.credential_file, 'r') as file:
                credentials = json.load(file)

            # Get necessary credentials from the JSON
            endpoint = credentials['url']  # Extract the endpoint
            access_key = credentials['accessKey']
            secret_key = credentials['secretKey']
            region = 'ap-southeast-1'  # Default region
            secure = False  # Assuming it's HTTP unless specified otherwise

            # Initialize the boto3 client for S3 (MinIO)
            session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region
            )

            # Create an S3 client for MinIO
            s3_client = session.client('s3',
                                       endpoint_url=endpoint,
                                       use_ssl=secure)

            return s3_client
        except (NoCredentialsError, PartialCredentialsError) as e:
            print(f"Credentials error: {e}")
        except Exception as e:
            print(f"Error initializing MinIO client: {e}")
            raise

    def createBucket(self, bucket_name):
        """
        Create a bucket in MinIO.
        """
        try:
            self.s3_client.create_bucket(Bucket=bucket_name)
            print(f"Bucket '{bucket_name}' created successfully.")
        except Exception as e:
            print(f"Error creating bucket '{bucket_name}': {e}")

    def listBuckets(self):
        """
        List all buckets in MinIO.
        """
        try:
            response = self.s3_client.list_buckets()
            print("Buckets:")
            for bucket in response['Buckets']:
                print(f"- {bucket['Name']}")
        except Exception as e:
            print(f"Error listing buckets: {e}")

    def uploadFile(self, bucket_name, file_path, object_name=None) -> bool:
        """
        Upload a file to a specific bucket.
        """
        try:
            if object_name is None or len(object_name) == 0:
                # Use file name as object name
                object_name = file_path.split('/')[-1]
                if object_name is None:
                    object_name = file_path

            print(f"HAHA {object_name}")
            self.s3_client.upload_file(file_path, bucket_name, object_name)
            print(
                f"File '{file_path}' uploaded to '{bucket_name}/{object_name}'.")
        except Exception as e:
            print(
                f"Error uploading file '{file_path}' to bucket '{bucket_name}': {e}")
            return False

        return True

    def listFilesInBucket(self, bucket_name):
        """
        List files in a specific bucket.
        """
        try:
            response = self.s3_client.list_objects_v2(Bucket=bucket_name)
            if 'Contents' in response:
                print(f"Files in bucket '{bucket_name}':")
                for obj in response['Contents']:
                    print(f"- {obj['Key']}")
            else:
                print(f"No files found in bucket '{bucket_name}'.")
        except Exception as e:
            print(f"Error listing files in bucket '{bucket_name}': {e}")
