from kikimr.public.sdk.python import client as ydb

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


def get_config():
    endpoint = os.getenv("endpoint")
    database = os.getenv("database")
    if endpoint is None or database is None:
        raise AssertionError("Нужно указать обе переменные окружения")
    credentials = ydb.construct_credentials_from_environ()
    return ydb.DriverConfig(endpoint, database, credentials=credentials)


def execute(config, query, params):
    with ydb.Driver(config) as driver:
        try:
            driver.wait(timeout=5)
        except TimeoutError:
            print("Connect failed to YDB")
            print("Last reported errors by discovery:")
            print(driver.discovery_debug_details())
            return None

        session = driver.table_client.session().create()
        prepared_query = session.prepare(query)

        return session.transaction(ydb.SerializableReadWrite()).execute(
            prepared_query,
            params,
            commit_tx=True
        )


def insert_link(id, link):
    config = get_config()
    query = """
        DECLARE $id AS Utf8;
        DECLARE $link AS Utf8;

        UPSERT INTO links (id, link) VALUES ($id, $link);
        """
    params = {'$id': id, '$link': link}
    execute(config, query, params)


def find_link(id):
    print(id)
    config = get_config()
    query = """
        DECLARE $id AS Utf8;

        SELECT link FROM links where id=$id;
        """
    params = {'$id': id}
    result_set = execute(config, query, params)
    if not result_set or not result_set[0].rows:
        return None

    return result_set[0].rows[0].link


def shorten(event):
    body = event.get('body')

    if body:
        body = decode(event, body)
        original_host = event.get('headers').get('Origin')
        link_id = hashlib.sha256(body.encode('utf8')).hexdigest()[:6]
        # в ссылке могут быть закодированные символы, например, %. это помешает работе api-gateway при редиректе,
        # поэтому следует избавиться от них вызовом urllib.parse.unquote
        insert_link(link_id, urllib.parse.unquote(body))
        return response(200, {'Content-Type': 'application/json'}, False, json.dumps({'url': f'{original_host}/r/{link_id}'}))

    return response(400, {}, False, 'В теле запроса отсутствует параметр url')


def redirect(event):
    link_id = event.get('pathParams').get('id')
    redirect_to = find_link(link_id)

    if redirect_to:
        return response(302, {'Location': redirect_to}, False, '')

    return response(404, {}, False, 'Данной ссылки не существует')


# эти проверки нужны, поскольку функция у нас одна
# в идеале сделать по функции на каждый путь в api-gw
def get_result(url, event):
    if url == "/shorten":
        return shorten(event)
    if url.startswith("/r/"):
        return redirect(event)

    return response(404, {}, False, 'Данного пути не существует')


def handler(event, context):
    url = event.get('url')
    if url:
        # из API-gateway url может прийти со знаком вопроса на конце
        if url[-1] == '?':
            url = url[:-1]
        return get_result(url, event)

    return response(404, {}, False, 'Эту функцию следует вызывать при помощи api-gateway')
