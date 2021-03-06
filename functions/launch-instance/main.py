#!/bin/env python

from __future__ import print_function
import json
import boto3
import botocore.exceptions
import logging
from datetime import datetime
import os
import base64
import time

# set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, datetime):
        serial = obj.isoformat()
        return serial
    raise TypeError ("Type not serializable")


def lambda_handler(event, context):
    """ Given an AMI identifier, launch a spot instance version of the image """
    logger.info('Received event: ' + json.dumps(event, default=json_serial, indent=2))

    # fetch parameters
    image_id = event['image_id']
    key_name = os.getenv('key_name', 'davidski_root')
    instance_profile = os.getenv('instance_profile', 'arn:aws:iam::754135023419:instance-profile/aws-packer-ec2')
    subnet_id = os.getenv('subnet_id', 'subnet-75bc4d12')
    security_group = os.getenv('security_group', 'sg-2a999d53')
    instance_type = os.getenv('instance_type', 'c3.large')


    # set user data to install Inspector agent
    user_data = (b"#!/bin/bash\n"
                 b"apt-get update\n"
                 b"apt-get install -y libcurl4-openssl-dev\n"
                 b"cd /tmp\n"
                 b"curl -O https://d1wk0tztpsntt1.cloudfront.net/linux/latest/install\n"
                 b"bash install\n"
                 b"")
    user_data = base64.b64encode(user_data).decode('ascii')

    # session = boto3.Session(profile_name='administrator-service')
    client = boto3.client('ec2')

    try:
        response = client.request_spot_instances(
            DryRun=False,
            InstanceCount=1,
            Type='one-time',
            SpotPrice='0.10',
            LaunchSpecification={
                'ImageId': image_id,
                'KeyName': key_name,
                'SecurityGroupIds': [security_group],
                'UserData': user_data,
                'InstanceType': instance_type,
                'BlockDeviceMappings': [
                    {
                        'DeviceName': 'sdb',
                        'VirtualName': 'ephemeral0'
                    }
                ],
                'IamInstanceProfile': {
                    'Arn': instance_profile
                },
                'SubnetId': subnet_id
            }
        )
        logger.info('Received response: ' + json.dumps(response, default=json_serial, indent=2))
    except botocore.exceptions.ClientError as e:
        logger.fatal("Unexpected error: %s" % e)
        raise
    else:
        spot_request_id=response['SpotInstanceRequests'][0]['SpotInstanceRequestId']

    # sleep briefly to allow the spot request to be available
    time.sleep(0.05)

    # create tags on the spot fleet request to be passed to the instance
    client.create_tags(
        Resources=[spot_request_id],
        Tags=[{
            'Key': 'project',
            'Value': 'infrastructure'
        }, {
            'Key': 'managed_by',
            'Value': 'lambda_function'
        }, {
            'Key': 'scan_batch',
            'Value': event['scan_batch_id']
        }]
    )

    return spot_request_id


if __name__ == '__main__':
    results = lambda_handler(event={'image_id': 'ami-c804d7a8'},
                             context="")
    print(results)
