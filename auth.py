import bcrypt
import mysql.connector
from db_utils import get_db_connection

def hash_password(password: str) -> str:
    # Generate a hashed version of the password
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain_password:str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def register_user(username: str, password: str, email: str, user_type:str):
        
    hashed = hash_password(password)
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        #Checks if username or email already exists
        cursor.execute("SELECT user_id FROM users WHERE username = %s OR email = %s", (username,email))
        if cursor.fetchone():
            return False  #User or email already exists
        
        # Insert new user
        cursor.execute(""" 
            INSERT INTO users(username, password_hash, email, user_type)
            VALUES (%s, %s, %s,%s)
        """, (username, hashed, email, user_type))
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"Registration failed: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def get_user_by_login(login_identifier: str):
    """ 
    Fetches a user by either their username or email address.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary= True)

    try:
        # Check against both username and email columns
        cursor.execute("SELECT * FROM users WHERE username = %s OR email =%s", (login_identifier,login_identifier))
        user = cursor.fetchone()
        return user
    except mysql.connector.Error as e:
        print(f"Error fetching user: {e}")
        return None
    finally:
        cursor.close()
        conn.close()
        