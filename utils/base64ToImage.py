import base64
from PIL import Image
from io import BytesIO

def base64_to_image(base64_string):
    if "data:image" in base64_string:
        base64_string = base64_string.split(",")[1]

    image_bytes = base64.b64decode(base64_string)
    return image_bytes

def create_image_from_bytes(image_bytes):
    image_stream = BytesIO(image_bytes)

    image = Image.open(image_stream)
    return image

def convert(img_string):
    base64_string = img_string
    image_bytes = base64_to_image(base64_string)
    img = create_image_from_bytes(image_bytes)
    return img

