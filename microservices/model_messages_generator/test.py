# from lib import ftp

# file_handler = ftp.FileTransferHandler(
#     bucket='test', max_size_mb=1024, json_credentials_file='credentials.json')
# result = file_handler.uploadFile(
#     file_path='turletbot3_plate.png', destination='')
# print(result)

# # buckets = file_handler.minio_client.s3_client.list_buckets()
# # print(buckets)

from minio import Minio

client = Minio(endpoint="103.166.183.191:9000",
               access_key="xR5gSOXjzpruRzF3nhro", secret_key="ZrMs9FQj97SLZgv1Plbj6LcdIzSaQamGkDdpfjtK", secure=False)

source_file = "turletbot3_plate.png"

# The destination bucket and filename on the MinIO server
bucket_name = "test"
destination_file = "images/turletbot3_plate.png"

# Make the bucket if it doesn't exist.
found = client.bucket_exists(bucket_name)
if not found:
    client.make_bucket(bucket_name)
    print("Created bucket", bucket_name)
else:
    print("Bucket", bucket_name, "already exists")

# Upload the file, renaming it in the process
client.fput_object(
    bucket_name, destination_file, source_file,
)
print(
    source_file, "successfully uploaded as object",
    destination_file, "to bucket", bucket_name,
)
