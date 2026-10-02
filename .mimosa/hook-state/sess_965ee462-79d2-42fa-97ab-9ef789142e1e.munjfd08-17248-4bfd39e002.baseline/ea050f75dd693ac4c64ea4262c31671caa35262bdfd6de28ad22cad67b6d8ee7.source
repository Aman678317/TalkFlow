#!/usr/bin/env python
import boto3
import logging
import json
import contextlib
from urllib.request import Request, urlopen
from uuid import uuid4
import tempfile
import os
from zipfile import ZipFile
import shutil

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CFN_SUCCESS = "SUCCESS"
CFN_FAILED = "FAILED"

s3 = boto3.client("s3")

def create(bucket_name, web_app_staging_object_prefix, web_app_root_object_prefix, object_key, object_content, object_content_type):
    workdir = tempfile.mkdtemp()
    raw_file_complete = os.path.join(workdir, object_key)
    with open(raw_file_complete, 'w') as f:
        f.write(object_content)

    zip_file_name = f"{os.path.splitext(object_key)[0]}.zip"
    zip_file_complete = os.path.join(workdir, zip_file_name)
    with ZipFile(zip_file_complete, mode='w') as zf:
        zf.write(raw_file_complete, arcname=object_key)

    s3.upload_file(zip_file_complete, bucket_name, f"{web_app_staging_object_prefix}{zip_file_name}")
    s3.upload_file(raw_file_complete, bucket_name, f"{web_app_root_object_prefix}{object_key}", 
                   ExtraArgs={'ContentType': object_content_type})
    shutil.rmtree(workdir)

def delete(bucket_name, web_app_staging_object_prefix, object_key):
    zip_file_name = f"{os.path.splitext(object_key)[0]}.zip"
    try:
        s3.delete_object(Bucket=bucket_name, Key=f"{web_app_staging_object_prefix}{zip_file_name}")
    except Exception as e:
        logger.warning(f"Error deleting object: {e}")

def handler(event, context):
    try:
        request_type = event['RequestType']
        props = event['ResourceProperties']
        physical_id = event.get('PhysicalResourceId', str(uuid4()))

        bucket_name = props["BucketName"]
        object_key = props["ObjectKey"]

        if request_type in ["Create", "Update"]:
            create(
                bucket_name, 
                props["WebAppStagingObjectPrefix"], 
                props["WebAppRootObjectPrefix"], 
                object_key,
                props.get("Content", ""), 
                props.get("ContentType", "text/javascript")
            )
        elif request_type == "Delete":
            delete(bucket_name, props["WebAppStagingObjectPrefix"], object_key)

        cfn_send(event, context, CFN_SUCCESS, physicalResourceId=physical_id)
    except Exception as e:
        logger.exception(e)
        cfn_send(event, context, CFN_FAILED, reason=str(e))

def cfn_send(event, context, responseStatus, responseData={}, physicalResourceId=None, reason=None):
    responseUrl = event['ResponseURL']
    responseBody = json.dumps({
        'Status': responseStatus,
        'Reason': reason or 'See CloudWatch Log Stream: ' + context.log_stream_name,
        'PhysicalResourceId': physicalResourceId or context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': responseData
    })
    headers = {'content-type': '', 'content-length': str(len(responseBody))}
    req = Request(responseUrl, method='PUT', data=responseBody.encode('utf-8'), headers=headers)
    with contextlib.closing(urlopen(req)):
        pass
