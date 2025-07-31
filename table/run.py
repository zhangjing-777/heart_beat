import os
from psycopg import connect
from dotenv import load_dotenv
load_dotenv()


dsn = os.getenv("DATABASE_URL") 
with open("init_sql.sql", "r", encoding="utf-8") as f:
    sql = f.read()

with connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

print("✅ 数据库初始化完成")