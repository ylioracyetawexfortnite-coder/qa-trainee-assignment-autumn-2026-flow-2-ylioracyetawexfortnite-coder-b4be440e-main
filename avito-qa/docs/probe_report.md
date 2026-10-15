# Probe report for https://qa-internship.avito.com

### register A
`POST /api/1/register` -> **201** (200 ms, application/json)
```
{"id": 74784, "username": "probe_a_bfed6929e2"}
```

### register A duplicate
`POST /api/1/register` -> **409** (193 ms, application/json)
```
{"error": "username is already registered"}
```

### register B
`POST /api/1/register` -> **201** (192 ms, application/json)
```
{"id": 74786, "username": "probe_b_bfed6929e2"}
```

### register empty body
`POST /api/1/register` -> **ERR** (0 ms, )
```
ReadTimeout(ReadTimeoutError("HTTPSConnectionPool(host='qa-internship.avito.com', port=443): Read timed out. (read timeout=15)"))
```

### register empty password
`POST /api/1/register` -> **400** (102 ms, application/json)
```
{"error": "invalid JSON body"}
```

### authorize A
`POST /api/1/autorize` -> **200** (180 ms, application/json)
```
{"accessToken": "***", "tokenType": "Bearer"}
```

### authorize B
`POST /api/1/autorize` -> **200** (200 ms, application/json)
```
{"accessToken": "***", "tokenType": "Bearer"}
```

### authorize wrong password
`POST /api/1/autorize` -> **400** (122 ms, application/json)
```
{"error": "invalid JSON body"}
```

### authorize unknown user
`POST /api/1/autorize` -> **401** (90 ms, application/json)
```
{"error": "invalid username or password"}
```

### create item
`POST /api/1/item` -> **200** (103 ms, application/json)
```
{"status": "Сохранили объявление - 91953b06-560d-4c63-9208-e6b038c2af3e"}
```

### create item without token
`POST /api/1/item` -> **401** (95 ms, application/json)
```
{"error": "valid bearer token is required"}
```

### create item foreign sellerID
`POST /api/1/item` -> **400** (126 ms, application/json)
```
{"result": {"message": "sellerID должен совпадать с идентификатором авторизованного пользователя", "messages": {}}, "status": "400"}
```

### create item X-UserId header
`POST /api/1/item` -> **400** (96 ms, application/json)
```
{"result": {"message": "sellerID должен совпадать с идентификатором авторизованного пользователя", "messages": {}}, "status": "400"}
```

### create negative price
`POST /api/1/item` -> **200** (92 ms, application/json)
```
{"status": "Сохранили объявление - cd59b344-a521-4127-87f4-3b7fdc853469"}
```

### create zero price
`POST /api/1/item` -> **400** (97 ms, application/json)
```
{"result": {"message": "поле price обязательно", "messages": {}}, "status": "400"}
```

### create empty name
`POST /api/1/item` -> **400** (93 ms, application/json)
```
{"result": {"message": "поле name обязательно", "messages": {}}, "status": "400"}
```

### create price as string
`POST /api/1/item` -> **400** (88 ms, application/json)
```
{"result": {"message": "", "messages": {}}, "status": "не передано тело объявления"}
```

### create price float
`POST /api/1/item` -> **400** (94 ms, application/json)
```
{"result": {"message": "", "messages": {}}, "status": "не передано тело объявления"}
```

### create negative likes
`POST /api/1/item` -> **200** (100 ms, application/json)
```
{"status": "Сохранили объявление - dd62fa2b-8e98-418e-b570-771518038747"}
```

### create no statistics
`POST /api/1/item` -> **400** (102 ms, application/json)
```
{"result": {"message": "поле likes обязательно", "messages": {}}, "status": "400"}
```

### create name 1000 chars
`POST /api/1/item` -> **200** (145 ms, application/json)
```
{"status": "Сохранили объявление - 0cc28c7f-6d88-4188-8c3b-15a5199e8738"}
```

### get item
`GET /api/1/item/91953b06-560d-4c63-9208-e6b038c2af3e` -> **200** (114 ms, application/json)
```
[{"createdAt": "2026-10-15 21:44:57.381678 +0300 +0300", "id": "91953b06-560d-4c63-9208-e6b038c2af3e", "name": "probe-bfed6929e2", "price": 9900, "sellerId": 74784, "statistics": {"contacts": 43, "likes": 21, "viewCount": 11}}]
```

### get item without token
`GET /api/1/item/91953b06-560d-4c63-9208-e6b038c2af3e` -> **401** (111 ms, application/json)
```
{"error": "valid bearer token is required"}
```

### get item by other user
`GET /api/1/item/91953b06-560d-4c63-9208-e6b038c2af3e` -> **200** (125 ms, application/json)
```
[{"createdAt": "2026-10-15 21:44:57.381678 +0300 +0300", "id": "91953b06-560d-4c63-9208-e6b038c2af3e", "name": "probe-bfed6929e2", "price": 9900, "sellerId": 74784, "statistics": {"contacts": 43, "likes": 21, "viewCount": 11}}]
```

### seller items
`GET /api/1/74784/item` -> **200** (106 ms, application/json)
```
[{"createdAt": "2026-10-15 21:44:57.381678 +0300 +0300", "id": "91953b06-560d-4c63-9208-e6b038c2af3e", "name": "probe-bfed6929e2", "price": 9900, "sellerId": 74784, "statistics": {"contacts": 43, "likes": 21, "viewCount": 11}}, {"createdAt": "2026-10-15 21:44:57.808022 +0300 +0300", "id": "cd59b344-a521-4127-87f4-3b7fdc853469", "name": "probe-bfed6929e2", "price": -1, "sellerId": 74784, "statistics": {"contacts": 43, "likes": 21, "viewCount": 11}}, {"createdAt": "2026-10-15 21:44:58.297764 +0300 +0300", "id": "dd62fa2b-8e98-418e-b570-771518038747", "name": "probe-bfed6929e2", "price": 9900, "s
```

### statistic v1
`GET /api/1/statistic/91953b06-560d-4c63-9208-e6b038c2af3e` -> **200** (106 ms, application/json)
```
[{"contacts": 43, "likes": 21, "viewCount": 11}]
```

### statistic v2
`GET /api/2/statistic/91953b06-560d-4c63-9208-e6b038c2af3e` -> **200** (97 ms, application/json)
```
[{"contacts": 43, "likes": 21, "viewCount": 11}]
```

### delete item v1 path
`DELETE /api/1/item/91953b06-560d-4c63-9208-e6b038c2af3e` -> **405** (95 ms, )
```

```

### delete foreign item
`DELETE /api/2/item/91953b06-560d-4c63-9208-e6b038c2af3e` -> **200** (101 ms, )
```

```

### get unknown item
`GET /api/1/item/7f815dba-be77-42fb-9394-fccef579e3a4` -> **404** (121 ms, application/json)
```
{"result": {"message": "item 7f815dba-be77-42fb-9394-fccef579e3a4 not found", "messages": null}, "status": "404"}
```

### get invalid id
`GET /api/1/item/abc` -> **400** (92 ms, application/json)
```
{"result": {"message": "ID айтема не UUID: abc", "messages": {}}, "status": "400"}
```

### seller items of B (empty)
`GET /api/1/74786/item` -> **200** (123 ms, application/json)
```
[]
```

### seller items invalid id
`GET /api/1/abc/item` -> **400** (104 ms, application/json)
```
{"result": {"message": "передан некорректный идентификатор продавца", "messages": {}}, "status": "400"}
```

### statistic unknown id v1
`GET /api/1/statistic/90818fb7-cd84-494a-9aa3-cafa9f19c84a` -> **404** (114 ms, application/json)
```
{"result": {"message": "statistic 90818fb7-cd84-494a-9aa3-cafa9f19c84a not found", "messages": null}, "status": "404"}
```

### statistic unknown id v2
`GET /api/2/statistic/c5d38647-02e5-4198-8ecc-a478d3219c67` -> **404** (90 ms, application/json)
```
{"result": {"message": "statistic c5d38647-02e5-4198-8ecc-a478d3219c67 not found", "messages": null}, "status": "404"}
```

### bad token
`GET /api/1/74784/item` -> **401** (109 ms, application/json)
```
{"error": "valid bearer token is required"}
```

### delete item v2
`DELETE /api/2/item/91953b06-560d-4c63-9208-e6b038c2af3e` -> **404** (144 ms, application/json)
```
{"result": {"message": "", "messages": null}, "status": "500"}
```

### delete item again
`DELETE /api/2/item/91953b06-560d-4c63-9208-e6b038c2af3e` -> **404** (97 ms, application/json)
```
{"result": {"message": "", "messages": null}, "status": "500"}
```

### get deleted item
`GET /api/1/item/91953b06-560d-4c63-9208-e6b038c2af3e` -> **404** (122 ms, application/json)
```
{"result": {"message": "item 91953b06-560d-4c63-9208-e6b038c2af3e not found", "messages": null}, "status": "404"}
```

### statistic deleted v1
`GET /api/1/statistic/91953b06-560d-4c63-9208-e6b038c2af3e` -> **200** (96 ms, application/json)
```
[{"contacts": 43, "likes": 21, "viewCount": 11}]
```

### statistic deleted v2
`GET /api/2/statistic/91953b06-560d-4c63-9208-e6b038c2af3e` -> **200** (115 ms, application/json)
```
[{"contacts": 43, "likes": 21, "viewCount": 11}]
```
