import urllib.parse
import hashlib
import base64
import json
import os


def decode(event, body):
    # тело запроса может быть закодировано
    is_base64_encoded = event.get('isBase64Encoded')
    if is_base64_encoded:
        body = str(base64.b64decode(body), 'utf-8')
    return body


def response(statusCode, headers, isBase64Encoded, body):
    return {
        'statusCode': statusCode,
        'headers': headers,
        'isBase64Encoded': isBase64Encoded,
        'body': body,
    }


def shorten(event):
    body = event.get('body')

    if body:
        body = decode(event, body)
        # тело запроса является строкой вида url=https://link.to/address
        original_host = event.get('headers').get('Origin')
        link_id = hashlib.sha256(body.encode('utf8')).hexdigest()[:6]
        # TODO положить ссылку в базу данных
        return response(200, {'Content-Type': 'application/json'}, False, json.dumps({'url': f'{original_host}/r/{link_id}'}))

    return response(400, {}, False, 'В теле запроса отсутствует параметр url')


def get_result(url, event):
    if url == "/shorten":
        return shorten(event)

    return response(404, {}, False, 'Данного пути не существует')


def handler(event, context):
    url = event.get('url')
    if url:
        # из API-gateway url может прийти со знаком вопроса на конце
        if url[-1] == '?':
            url = url[:-1]
        return get_result(url, event)

    return response(404, {}, False, 'Эту функцию следует вызывать при помощи api-gateway')
