import configparser
import os
import boto3
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import qrcode
import random
import string
import requests
from PIL import Image as PILImage
from io import BytesIO
import uuid

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
dynamodb = session.client('dynamodb', region_name='us-east-1')  
s3 = session.client('s3',region_name='us-east-1')

aws_s3_bucket_name = "sold-tickets"
queueUrlRequest = 'https://sqs.us-east-1.amazonaws.com/392492183407/cola-entrada.fifo'
queueUrlResponse = 'https://sqs.us-east-1.amazonaws.com/392492183407/cola-salida.fifo'
queueToken = 'https://sqs.us-east-1.amazonaws.com/392492183407/cola-token.fifo'


def upload_to_s3(local_file, s3_path):
    try:
        s3.upload_file(local_file, aws_s3_bucket_name, s3_path)
        return True
    except FileNotFoundError:
        return False

def enviar_mensaje(path,user_id,id_compra,query):
    # Envía el mensaje a la cola
    print("USER ID",user_id)
    sqs.send_message(
        QueueUrl=queueUrlResponse,
        MessageBody=query+";"+ path+";"+user_id+";"+id_compra,
        MessageGroupId= user_id
    )

def getURLImage(claveEvento):
    tabla_nombre = 'Eventos'
    print(claveEvento)
    clave_primaria = {
        'eventos': {'S': claveEvento.strip()}
    }

    response = dynamodb.get_item(TableName=tabla_nombre, Key=clave_primaria)

    item = response.get('Item', {})
    URLImagePDF = item.get('URLImage', {'S':""})["S"]
    return URLImagePDF

def receiveToken():
    notToken = True
    while(notToken):
        # Recibe hasta 10 mensajes de la cola especificada
        response = sqs.receive_message(
            QueueUrl=queueToken,
            AttributeNames=['All'],
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20
        )

        # Verifica si se recibieron mensajes
        if 'Messages' in response:
            mensajes = response['Messages']

            for mensaje in mensajes:
                mensaje = str(mensaje['Body'])
                print("TOKEN recibido:", mensaje)
                receipt_handle = response['Messages'][0]['ReceiptHandle']

                # Borra el mensaje de la cola para que no se reciba nuevamente
                sqs.delete_message(
                    QueueUrl=queueToken,
                    ReceiptHandle=receipt_handle
                )
            notToken = False
        else:
            print("No se recibe el TOKEN")

            

def sendToken():
    sqs.send_message(
        QueueUrl=queueToken,
        MessageBody="TOKEN",
        MessageGroupId= str(uuid.uuid4())
    )
    print("TOKEN ENVIADO")

def checkDatabase(numTickets, claveEvento):
    tabla_nombre = 'Eventos'
    print(claveEvento)
    clave_primaria = {
        'eventos': {'S': claveEvento.strip()}
    }

    response = dynamodb.get_item(TableName=tabla_nombre, Key=clave_primaria)

    
    item = response.get('Item', {})
    print(item)
    ticketsVendidos = item.get('TicketsVendidos', {'N': '0'})["N"]
    ticketsMax = item.get('NumMaxTickets', {'N': '0'})["N"]

    print(f"TICKETS MAX: {ticketsMax}, TICKETS VENDIDOS: {ticketsVendidos}")
    nuevos_tickets_vendidos = int(ticketsVendidos) + numTickets

    if nuevos_tickets_vendidos<= int(ticketsMax):
        print("if")
        # Actualiza el campo 'Tickets vendidos'

        actualizacion = {
            'UpdateExpression': 'SET TicketsVendidos = :val1',
            'ExpressionAttributeValues': {
                ':val1': {'N': str(nuevos_tickets_vendidos)}
            },
            'TableName': tabla_nombre,
            'Key': clave_primaria
        }
         # Realiza la actualización
        try:
            response = dynamodb.update_item(**actualizacion)
            print("Elemento actualizado con éxito.")
        except Exception as e:
            print("Error al actualizar el elemento:", e)
        return True
    
    return False

def leer_mensajes_sqs():
        while(True):
            # Recibe hasta 10 mensajes de la cola especificada
            response = sqs.receive_message(
                QueueUrl=queueUrlRequest,
                AttributeNames=['All'],
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20
            )

            # Verifica si se recibieron mensajes
            if 'Messages' in response:
                mensajes = response['Messages']
                for mensaje in mensajes:
                    # Procesa el mensaje (en este ejemplo, simplemente imprimimos el cuerpo del mensaje)
                    mensaje = str(mensaje['Body'])
                    args = []
                    args = mensaje.split(";")

                    print(args)

                    print("Mensaje recibido:", mensaje)
                    receipt_handle = response['Messages'][0]['ReceiptHandle']

                    # Borra el mensaje de la cola para que no se reciba nuevamente
                    sqs.delete_message(
                        QueueUrl=queueUrlRequest,
                        ReceiptHandle=receipt_handle
                    )

                    event = args[0]
                    nameClient = args[1]                    
                    numTickets = int(args[2])
                    user_id = args[3]
                    
                    
                    #COMPROBAR TOKEN ANTES DE ACCEDER A LA DYNAMO PARA VER LOS VENDIDOS
                    receiveToken()

                    if checkDatabase(numTickets, event):
                        sendToken()
                        purchase_number = generar_id_compra()
                        output_filename = purchase_number + ".pdf" #el nombre del fichero es el id de compra
                        generate_ticket(event, nameClient, purchase_number, numTickets,output_filename)
                        enviar_mensaje(event,user_id,purchase_number, "ok") #Enviamos la respuesta


                    else :                    
                        sendToken()  
                        enviar_mensaje(event,user_id, "","error") #Enviamos la respuesta

            else:
                print("No se recibieron mensajes en la cola.")


def generar_id_compra():
    longitud = 20  # Puedes ajustar la longitud de tu ID de compra aquí
    caracteres = string.ascii_letters + string.digits  # Letras y números
    id_compra = ''.join(random.choice(caracteres) for _ in range(longitud))
    return id_compra

def download_image(url):
    response = requests.get(url)
    if response.status_code == 200:
        img = PILImage.open(BytesIO(response.content))
        return img

def create_qr_code(data, filename):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(filename)

def generate_ticket(event_name, buyer_name, purchase_number, num_tickets,output_filename):
    doc = SimpleDocTemplate(output_filename, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    qr_data = f"Evento: {event_name}\nComprador: {buyer_name}\nNúmero de Compra: {purchase_number}"
    URLImage = getURLImage(event_name)
    for i in range(num_tickets):
        elements.append(Paragraph(f"{event_name}", styles['Title']))
        elements.append(Spacer(1, 0.5 * inch))
      
        # Load the image from a URL
        img = download_image(URLImage)
        if img:
            img_path = f"img_{i}.jpg"
            img.save(img_path, "JPEG")
            elements.append(Image(img_path, width=7 * inch, height=4 * inch))

        elements.append(Spacer(1, 0.25 * inch))
        elements.append(Paragraph(f"{buyer_name}", styles['Normal']))
        elements.append(Paragraph(f"ID de Compra: {purchase_number}", styles['Normal']))
        elements.append(Spacer(1, 0.25 * inch))
        elements.append(Paragraph(f"Entrada {i+1}", styles['Title']))
        elements.append(Spacer(1, 0.25 * inch))

        # Generate and add QR code to the PDF
        qr_filename = f"qr_code_{i}.png"
        create_qr_code(qr_data, qr_filename)
        elements.append(Image(qr_filename, width=1.5 * inch, height=1.5 * inch))

        # Page break for the next ticket
        if i < num_tickets - 1:
            elements.append(PageBreak())

    # Build the PDF
    doc.build(elements)

    # Upload the PDF to S3
    if upload_to_s3(output_filename, f'{event_name}/{output_filename}'):
        print(f'El archivo PDF se subió correctamente a S3: {event_name}/{output_filename}')
    else:
        print('Error al subir el archivo PDF a S3.')

    # Eliminar archivos locales
    #TO-DO DESCOMENTAR BORRARLO
    os.remove(output_filename)
    
    for i in range(num_tickets):
        img_path = f"img_{i}.jpg"
        os.remove(img_path)
        qr_filename = f"qr_code_{i}.png"
        os.remove(qr_filename)

if __name__ == '__main__':
    leer_mensajes_sqs()
    
