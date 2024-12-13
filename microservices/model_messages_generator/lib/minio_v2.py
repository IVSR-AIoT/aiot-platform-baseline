from minio import Minio


class MinioClient:
    def __init__(self, endpoint: str, access_key: str, secret_key: str):
        self.minio_client = Minio(
            endpoint=endpoint, access_key=access_key, secret_key=secret_key, secure=False)

    def uploadFile(self, bucket_name: str, file_path: str, object_name: str) -> bool:
        try:
            self.minio_client.fput_object(
                bucket_name=bucket_name, object_name=object_name, file_path=file_path)
        except Exception as e:
            print(f"{e}")
            return False

        return True
