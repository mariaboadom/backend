import boto3
sqs = boto3.client('sqs',region_name='us-east-1')
queueToken = 'https://sqs.us-east-1.amazonaws.com/392492183407/cola-token.fifo'
import uuid


def sendToken():
    sqs.send_message(
        QueueUrl=queueToken,
        MessageBody="TOKEN",
        MessageGroupId= str(uuid.uuid4())
    )

if __name__ == '__main__':
    sendToken()