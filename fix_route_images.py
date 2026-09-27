import os
from dotenv import load_dotenv
import psycopg2

base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, '.env'))

conn = psycopg2.connect(
    host=os.environ['SUPABASE_DB_HOST'],
    port=os.environ.get('SUPABASE_DB_PORT', '5432'),
    database=os.environ.get('SUPABASE_DB_NAME', 'postgres'),
    user=os.environ['SUPABASE_DB_USER'],
    password=os.environ['SUPABASE_DB_PASSWORD'],
)
cur = conn.cursor()

cur.execute('SELECT id, route_name, pickup_city, drop_city FROM route_prices ORDER BY id')
rows = cur.fetchall()

for route_id, route_name, pickup_city, drop_city in rows:
    text = f'{route_name} {pickup_city} {drop_city}'.lower()
    if any(k in text for k in [
        'madurai', 'thiruvannamalai', 'trichy', 'thanjavur', 'kumbakonam',
        'kanchipuram', 'palani', 'rameswaram', 'kanyakumari', 'temple', 'murugan'
    ]):
        new_url = '/static/img/route-temple.svg?v=3'
    elif any(k in text for k in [
        'cuddalore', 'chennai', 'mahabalipuram', 'puducherry', 'coast', 'beach',
        'harbor', 'sea', 'shore'
    ]):
        new_url = '/static/img/route-coast.svg?v=3'
    elif any(k in text for k in [
        'ooty', 'kodaikanal', 'yercaud', 'yelagiri', 'nilgiris', 'coimbatore',
        'bangalore', 'hill', 'mountain'
    ]):
        new_url = '/static/img/route-hills.svg?v=3'
    else:
        new_url = '/static/img/route-city.svg?v=3'
    cur.execute('UPDATE route_prices SET image_url = %s WHERE id = %s', (new_url, route_id))

conn.commit()
print('Updated route image URLs')
conn.close()
