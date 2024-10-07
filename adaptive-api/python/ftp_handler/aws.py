import boto3


def singleBinaryObjectUpload(_bucket: str, _src_bytes: bytes, _destination_obj: str) -> bool:
    """
    Uploads a file to the bucket:
    _bucket: S3 bucket name |
    _src_bytes: Binary form of object (image/JPEG or video/MP4) |
    _destination_obj: The path to the object in S3 bucket
    """
    try:
        client = boto3.client('s3')

        res = client.put_object(
            Bucket=_bucket,
            Key=_destination_obj,
            Body=_src_bytes)
    except Exception as e:
        print(f"Error when upload to S3: {e}")
        return False

    if res == None:
        return False
    return True


def singleFileUpload(_bucket: str, _file: str, _des: str) -> bool:
    """
    Uploads a file to the bucket:
    _bucket: S3 bucket name |
    _file: Path to file |
    _des: Path to the object in S3 bucket
    """
    try:
        client = boto3.client('s3')

        res = client.put_object(
            Bucket=_bucket,
            Key=_des,
            Body=_file
        )
    except Exception as e:
        print(f"Error when upload to S3: {e}")
        return False

    if res == None:
        return False
    return True
