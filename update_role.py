import sqlite3

# Connect to your SQLite database
conn = sqlite3.connect("consultations.db")
cursor = conn.cursor()

# Update the role from 'user' to 'admin' where username is 'admin'
cursor.execute("UPDATE users SET role = 'admin' WHERE username = 'admin'")
conn.commit()

# Confirm the change
cursor.execute("SELECT * FROM users WHERE username = 'admin'")
admin_user = cursor.fetchone()
print("Updated admin user:", admin_user)

# Close the connection
conn.close()
