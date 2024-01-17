import boto3
queueToken = 'https://sqs.us-east-1.amazonaws.com/392492183407/cola-token.fifo'
import uuid
import configparser



credentials_file = './environment/credentials'

# Crear un objeto de configuración e interpretar el archivo
config = configparser.ConfigParser()
config.read(credentials_file)

# Obtener las credenciales del archivo
aws_access_key_id = config.get('default', 'aws_access_key_id')
aws_secret_access_key = config.get('default', 'aws_secret_access_key')
aws_session_token = config.get('default','aws_session_token')

# Configurar las credenciales en boto3
session = boto3.Session(
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    aws_session_token = aws_session_token,
    region_name='us-east-1'  # Cambia a la región deseada
)

sqs = session.client('sqs',region_name='us-east-1')

def sendToken():
    sqs.send_message(
        QueueUrl=queueToken,
        MessageBody="TOKEN",
        MessageGroupId= str(uuid.uuid4())
    )

if __name__ == '__main__':
    sendToken()