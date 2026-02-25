import json
import mysql.connector

# 1️⃣ Wczytanie JSON
with open("users.json", "r") as f:
    users_json = json.load(f)

# 2️⃣ Połączenie z Railway MySQL
db = mysql.connector.connect(
    host="mysql.railway.internal",
    user="root",
    password="BSuyYjHMSxMcHjDtXnsXqGQjfBcKlTaX",
    database="railway"
)

cursor = db.cursor()

# 3️⃣ Wstawianie danych z JSON do tabeli users
for key, user in users_json.items():
    username = user["username"]
    password = user["password"]
    balance = user.get("balance", 0)  # jeśli brak, domyślnie 0
    role = user["role"]

    sql = "INSERT INTO users (username, password, balance, role) VALUES (%s, %s, %s, %s)"
    val = (username, password, balance, role)
    cursor.execute(sql, val)

db.commit()  # zapisuje zmiany w bazie
print("Wszyscy użytkownicy dodani!")

# 4️⃣ Sprawdzenie
cursor.execute("SELECT * FROM users")
for row in cursor.fetchall():
    print(row)