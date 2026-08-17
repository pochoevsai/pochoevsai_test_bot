import httpx, json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'ru-RU,ru;q=0.9',
}

# Яндекс Маркет поиск
url = 'https://market.yandex.ru/api/v1/search?text=кроссовки&count=3&page=1'

r = httpx.get(url, headers=headers, timeout=10)
print('Yandex Market status:', r.status_code)

# Try their product API
url2 = 'https://api.partner.market.yandex.ru/v2/search?query=кроссовки'
r2 = httpx.get(url2, headers=headers, timeout=10)
print('Yandex Partner API:', r2.status_code)

# Try price comparison API
url3 = 'https://market.yandex.ru/search?text=339395807&cvredirect=2'
r3 = httpx.get(url3, headers=headers, timeout=10, follow_redirects=True)
print('Yandex search:', r3.status_code, len(r3.text))
