import os
import pyodbc
import asyncio
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from hypercorn.config import Config
from hypercorn.asyncio import serve
from claude_integration import ClaudeSQLAssistant

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Initialize Claude assistant
claude_assistant = ClaudeSQLAssistant()

# Database configuration
DB_CONFIG = {
    'server': os.getenv('MSSQL_SERVER', 'localhost'),
    'database': os.getenv('MSSQL_DATABASE', 'TransactionDB'),
    'username': os.getenv('MSSQL_USER', 'mcpuser'),
    'password': os.getenv('MSSQL_PASSWORD', 'StrongPassword123!')
}

def get_connection_string(config):
    return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={config['server']};DATABASE={config['database']};UID={config['username']};PWD={config['password']}"

def get_db_connection():
    try:
        conn = pyodbc.connect(get_connection_string(DB_CONFIG))
        return conn
    except pyodbc.Error as e:
        print(f"Error connecting to database: {str(e)}")
        return None

def get_table_names():
    try:
        conn = get_db_connection()
        if not conn:
            return []
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_TYPE = 'BASE TABLE'
        """)
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return tables
    except pyodbc.Error as e:
        print(f"Error getting table names: {str(e)}")
        return []

def get_table_columns(table_name):
    try:
        conn = get_db_connection()
        if not conn:
            return []
        
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT COLUMN_NAME, DATA_TYPE 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = ?
        """, table_name)
        columns = [{'name': row[0], 'type': row[1]} for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return columns
    except pyodbc.Error as e:
        print(f"Error getting column names: {str(e)}")
        return []

def execute_query(query, params=None):
    try:
        conn = get_db_connection()
        if not conn:
            return None
        
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        # Get column names
        columns = [column[0] for column in cursor.description]
        
        # Fetch results and handle datetime serialization
        results = []
        for row in cursor.fetchall():
            row_dict = {}
            for i, value in enumerate(row):
                # Convert datetime objects to ISO format strings
                if hasattr(value, 'isoformat'):
                    row_dict[columns[i]] = value.isoformat()
                else:
                    row_dict[columns[i]] = value
            results.append(row_dict)
        
        cursor.close()
        conn.close()
        return results
    except pyodbc.Error as e:
        print(f"Error executing query: {str(e)}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/tables')
def get_tables():
    try:
        tables = get_table_names()
        table_info = {}
        
        # Get column information for each table
        for table in tables:
            columns = get_table_columns(table)
            table_info[table] = [col['name'] for col in columns]
        
        # Update Claude with table information
        claude_assistant.update_table_info(table_info)
        
        return jsonify(tables)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/natural-query', methods=['POST'])
def natural_language_query():
    try:
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'No query provided'}), 400
        
        # First ensure we have table information
        tables = get_table_names()
        if not tables:
            return jsonify({'error': 'No tables found in the database'}), 500
            
        table_info = {}
        for table in tables:
            columns = get_table_columns(table)
            table_info[table] = [col['name'] for col in columns]
        
        # Update Claude with table information
        claude_assistant.update_table_info(table_info)
        
        # Generate SQL query from natural language
        try:
            sql_query = claude_assistant.generate_sql_query(data['query'])
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        # Execute the generated SQL query
        results = execute_query(sql_query)
        if results is None:
            return jsonify({'error': 'Failed to execute query'}), 500
        
        # Analyze results using Claude
        analysis = claude_assistant.analyze_results(data['query'], results)
        
        return jsonify({
            'sql_query': sql_query,
            'results': results,
            'analysis': analysis
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/query', methods=['POST'])
def execute_custom_query():
    try:
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'No query provided'}), 400
            
        query = data['query']
        results = execute_query(query)
        if results is None:
            return jsonify({'error': 'Failed to execute query'}), 500
            
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

async def main():
    config = Config()
    config.bind = ["localhost:5000"]
    await serve(app, config)

if __name__ == "__main__":
    asyncio.run(main()) 