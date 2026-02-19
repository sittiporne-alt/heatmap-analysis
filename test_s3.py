import requests
import pandas as pd

# URL ของไฟล์ JSON ที่อยู่บน S3
url = "https://website-onecharge.s3.ap-southeast-1.amazonaws.com/analysis/station_202602182357.json"

# ส่ง HTTP GET ไปดึงข้อมูล
response = requests.get(url)

# ถ้าโหลดสำเร็จ
if response.status_code == 200:
    data = response.json()  # แปลงเป็น Python object

    # แปลงเป็น DataFrame
    station_df = pd.json_normalize(data["station"])
    
    print("Loaded station master data successfully!")
    print(station_df.head())
else:
    print("Failed to fetch data. Status code:", response.status_code)
