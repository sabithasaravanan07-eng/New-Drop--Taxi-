from app import app

client = app.test_client()
response = client.get('/')
print(response.status_code)
print('Popular Routes & Prices' in response.get_data(as_text=True))