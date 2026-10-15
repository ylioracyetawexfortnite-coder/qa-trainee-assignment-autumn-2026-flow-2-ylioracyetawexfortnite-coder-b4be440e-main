"""JSON-схемы успешных ответов."""

REGISTER_RESPONSE = {
    "type": "object",
    "required": ["id", "username"],
    "properties": {
        "id": {"type": "integer", "minimum": 1},
        "username": {"type": "string", "minLength": 1},
    },
}

AUTHORIZE_RESPONSE = {
    "type": "object",
    "required": ["accessToken", "tokenType"],
    "properties": {
        "accessToken": {"type": "string", "minLength": 10},
        "tokenType": {"type": "string"},
    },
}

STATISTICS = {
    "type": "object",
    "required": ["likes", "viewCount", "contacts"],
    "properties": {
        "likes": {"type": "integer", "minimum": 0},
        "viewCount": {"type": "integer", "minimum": 0},
        "contacts": {"type": "integer", "minimum": 0},
    },
}
