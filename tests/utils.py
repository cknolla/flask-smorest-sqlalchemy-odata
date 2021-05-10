import json


def parse_response(response):
    return json.loads(response.get_data(as_text=True))
