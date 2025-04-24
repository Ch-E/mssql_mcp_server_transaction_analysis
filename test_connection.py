import pyodbc
import os

config = {
    "server": os.getenv("MSSQL_HOST", "localhost"),
    "user": os.getenv("MSSQL_USER", "mcpuser"),
    "password": os.getenv("MSSQL_PASSWORD", "StrongPassword123!"),
    "database": os.getenv("MSSQL_DATABASE", "TransactionDB")
}

def get_connection_string(config):
    """Create a connection string for pyodbc."""
    return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={config['server']};DATABASE={config['database']};UID={config['user']};PWD={config['password']}"

try:
    print("Attempting to connect to SQL Server...")
    conn = pyodbc.connect(get_connection_string(config))
    cursor = conn.cursor()
    print("Connection successful!")
    
    print("\nTesting query execution...")
    cursor.execute("SELECT TOP 1 * FROM INFORMATION_SCHEMA.TABLES")
    row = cursor.fetchone()
    print(f"Query result: {row}")
    
    cursor.close()
    conn.close()
    print("\nConnection test completed successfully!")
except Exception as e:
    print(f"Error: {str(e)}")
