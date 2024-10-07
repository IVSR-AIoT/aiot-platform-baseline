import aws
import os
import concurrent.futures

MB_TO_BYTES = 1024*1024


# def runWithTimeout(func: function, timeout: int, handler: function, *args, **kwargs):
#     with concurrent.futures.ThreadPoolExecutor() as executor:
#         future = executor.submit(func, *args, **kwargs)
#         try:
#             result = future.result(timeout=timeout)
#             return result
#         except concurrent.futures.TimeoutError:
#             handler()


def fileCheck(file_path: str, max_size_mb: int) -> bool:
    if not (os.path.isfile(file_path)):
        return False

    file_size_mb = os.path.getsize(file_path) / MB_TO_BYTES
    if file_size_mb > max_size_mb:
        return False

    return True


class FileTransferHandler:
    def __init__(self, bucket: str, max_size_mb: int,  timeout=60):
        self.bucket = bucket
        self.max_file_size_mb = max_size_mb
        # self.timeout = timeout

    def uploadFile(self, file_path: str, destination: str) -> bool:
        if not fileCheck(file_path):
            print("[ERROR]: File check failed: {}", file_path)
            return False

        result = aws.singleFileUpload(self.bucket, file_path, destination)

        # result = runWithTimeout(aws.singleFileUpload, self.timeout,
        #                         timeoutHandler, self.bucket, file_path, destination)

        return result
