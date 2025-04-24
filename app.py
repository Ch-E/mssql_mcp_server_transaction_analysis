from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import os
import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve
from functools import wraps
import pyodbc
from dotenv import load_dotenv
import json
from datetime import datetime
import subprocess
import sys
import openai
from typing import Optional, Dict, Any
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration from environment variables
config = {
    "server": os.getenv("MSSQL_SERVER", "localhost"),
    "user": os.getenv("MSSQL_USER", "mcpuser"),
    "password": os.getenv("MSSQL_PASSWORD", "StrongPassword123!"),
    "database": os.getenv("MSSQL_DATABASE", "TransactionDB"),
    "openai_api_key": os.getenv("OPENAI_API_KEY")
}

# Initialize OpenAI client
client = openai.OpenAI(api_key=config["openai_api_key"])

def get_connection_string(config):
    """Create a connection string for pyodbc."""
    return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={config['server']};DATABASE={config['database']};UID={config['user']};PWD={config['password']}"

def get_table_names():
    """Get all table names from the database."""
    try:
        conn = pyodbc.connect(get_connection_string(config))
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
    except Exception as e:
        print(f"Error getting table names: {e}")
        return []

def get_table_columns(table_name):
    """Get all column names for a specific table."""
    try:
        conn = pyodbc.connect(get_connection_string(config))
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = '{table_name}'
        """)
        columns = [(row[0], row[1]) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return columns
    except Exception as e:
        print(f"Error getting columns for table {table_name}: {e}")
        return []

def execute_sql_query(query):
    """Execute a SQL query and return the results."""
    try:
        # Validate the query before execution
        if not query.strip():
            raise ValueError("Empty query provided")
            
        # Check for potentially dangerous operations
        dangerous_operations = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE']
        if any(op in query.upper() for op in dangerous_operations):
            raise ValueError("This operation is not allowed for security reasons. Please use SELECT queries only.")
            
        # Get database connection
        conn = pyodbc.connect(get_connection_string(config))
        cursor = conn.cursor()
        
        try:
            cursor.execute(query)
            
            # Get column names and types
            columns = []
            for column in cursor.description:
                columns.append({
                    'name': column[0],
                    'type': str(column[1])
                })
            
            # Fetch all rows and convert to list of dictionaries
            rows = []
            for row in cursor.fetchall():
                row_dict = {}
                for i, value in enumerate(row):
                    # Convert datetime objects to strings
                    if hasattr(value, 'strftime'):
                        value = value.strftime('%Y-%m-%d %H:%M:%S')
                    # Convert Decimal objects to float
                    elif hasattr(value, 'as_integer_ratio'):  # This checks for Decimal type
                        value = float(value)
                    # Convert None to 'NULL' string
                    elif value is None:
                        value = 'NULL'
                    row_dict[columns[i]['name']] = value
                rows.append(row_dict)
            
            return {
                'columns': columns,
                'rows': rows,
                'row_count': len(rows)
            }
        except pyodbc.Error as e:
            raise ValueError(f"Database error: {str(e)}")
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        print(f"Error executing query: {e}")
        raise

def is_sql_query(text):
    """Check if the text looks like a SQL query."""
    sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP']
    return any(keyword in text.upper() for keyword in sql_keywords)

def is_transaction_query(text):
    """Check if the text is related to transaction analysis."""
    transaction_keywords = ['transaction', 'transactions', 'payment', 'payments', 'sale', 'sales', 'purchase', 'purchases']
    return any(keyword in text.lower() for keyword in transaction_keywords)

async def get_openai_response(message: str, include_schema: bool = False) -> str:
    """Get response from OpenAI API."""
    try:
        # If we need to include schema information
        schema_info = ""
        if include_schema:
            tables = get_table_names()
            schema_info = "Available data includes:\n"
            for table in tables:
                columns = get_table_columns(table)
                schema_info += f"\n{table}:\n"
                for col_name, col_type in columns:
                    schema_info += f"- {col_name} ({col_type})\n"

        system_message = """You are a business intelligence assistant that helps users understand their data through natural conversation. 
        Your role is to:
        1. Understand business questions and translate them into data analysis
        2. Provide clear, non-technical explanations of the data
        3. Highlight important business insights and trends
        4. Make recommendations based on the data
        
        When responding to queries:
        - Use plain, business-friendly language
        - Focus on business impact and insights
        - Avoid technical terms unless necessary
        - Provide context and recommendations
        - Use examples and comparisons to explain trends
        
        For data presentation:
        - Use simple, clear visualizations
        - Focus on key metrics that matter to business
        - Highlight trends and patterns
        - Compare performance over time
        - Show relationships between business metrics
        
        Response format:
        1. Clear explanation of what the data shows
        2. Key business insights
        3. Visual representation (if helpful)
        4. Recommendations or next steps
        5. Any important context or limitations
        
        Remember:
        - Focus on business value
        - Use simple, clear language
        - Provide actionable insights
        - Explain trends in business terms
        - Highlight opportunities and risks"""

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"{schema_info}\n\n{message}"}
        ]

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error getting OpenAI response: {e}")
        return "I apologize, but I'm having trouble processing your request right now. Please try again later."

def extract_sql_query(response: str) -> str:
    """Extract SQL query from OpenAI response."""
    try:
        # Look for SQL code blocks
        if "```sql" in response:
            start = response.find("```sql") + 6
            end = response.find("```", start)
            if end != -1:
                return response[start:end].strip()
        # Look for regular code blocks
        elif "```" in response:
            start = response.find("```") + 4
            end = response.find("```", start)
            if end != -1:
                return response[start:end].strip()
        return None
    except Exception:
        return None

def async_route(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper

@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')

def format_query_response(query_result, query_type="table", explanation=""):
    """Format the query result in a business-friendly way."""
    try:
        # Convert to pandas DataFrame for easier manipulation
        df = pd.DataFrame(query_result['rows'])
        
        if query_type == "table":
            # Create an HTML table with business-friendly styling
            table_html = df.to_html(
                classes='table table-striped table-bordered table-hover',
                index=False,
                border=1
            )
            return {
                "type": "table",
                "content": table_html,
                "row_count": len(df),
                "explanation": explanation
            }
        elif query_type == "bar":
            # Create a business-focused bar chart
            fig = px.bar(df, x=df.columns[0], y=df.columns[1],
                        title=f"Business Performance: {df.columns[1]} by {df.columns[0]}",
                        labels={df.columns[0]: df.columns[0], df.columns[1]: df.columns[1]})
            fig.update_layout(
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12),
                xaxis_title="Category",
                yaxis_title="Value"
            )
            return {
                "type": "chart",
                "content": json.dumps(fig, cls=PlotlyJSONEncoder),
                "chart_type": "bar",
                "explanation": explanation
            }
        elif query_type == "line":
            # Create a business trend line chart
            fig = px.line(df, x=df.columns[0], y=df.columns[1],
                         title=f"Business Trend: {df.columns[1]} over {df.columns[0]}",
                         labels={df.columns[0]: df.columns[0], df.columns[1]: df.columns[1]})
            fig.update_layout(
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12),
                xaxis_title="Time Period",
                yaxis_title="Value"
            )
            return {
                "type": "chart",
                "content": json.dumps(fig, cls=PlotlyJSONEncoder),
                "chart_type": "line",
                "explanation": explanation
            }
        elif query_type == "pie":
            # Create a business distribution pie chart
            fig = px.pie(df, values=df.columns[1], names=df.columns[0],
                        title=f"Business Distribution: {df.columns[1]} by {df.columns[0]}")
            fig.update_layout(
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=12)
            )
            return {
                "type": "chart",
                "content": json.dumps(fig, cls=PlotlyJSONEncoder),
                "chart_type": "pie",
                "explanation": explanation
            }
        else:
            # Default to table if no specific type is requested
            return format_query_response(query_result, "table", explanation)
    except Exception as e:
        print(f"Error formatting response: {e}")
        return {
            "type": "error",
            "content": str(e)
        }

def determine_visualization_type(query, result):
    """Determine the best visualization type based on the query and result."""
    query_lower = query.lower()
    
    # Check for aggregation keywords
    if any(word in query_lower for word in ["sum(", "count(", "avg(", "max(", "min("]):
        if "group by" in query_lower:
            return "bar"
        return "table"
    
    # Check for time series data
    if any(word in query_lower for word in ["date", "time", "year", "month", "day"]):
        return "line"
    
    # Check for distribution data
    if any(word in query_lower for word in ["distribution", "percentage", "proportion"]):
        return "pie"
    
    # Check for relationship data
    if any(word in query_lower for word in ["correlation", "relationship", "compare"]):
        return "scatter"
    
    # Default to table
    return "table"

@app.route('/api/chat', methods=['POST'])
@async_route
async def chat():
    """Handle chat messages and route to appropriate handler."""
    try:
        if not request.is_json:
            return jsonify({"type": "error", "content": "Request must be JSON"}), 400

        data = request.json
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({"type": "error", "content": "No message provided"}), 400

        # If it's a direct SQL query, execute it
        if is_sql_query(message):
            try:
                result = execute_sql_query(message)
                viz_type = determine_visualization_type(message, result)
                formatted_result = format_query_response(result, viz_type)
                return jsonify(formatted_result)
            except Exception as e:
                error_msg = str(e)
                if "Database error" in error_msg:
                    return jsonify({
                        "type": "error", 
                        "content": f"Database error: {error_msg.split('Database error: ')[-1]}"
                    })
                return jsonify({"type": "error", "content": f"Error executing SQL query: {error_msg}"})

        # For natural language queries
        try:
            # Get response from OpenAI with schema information for transaction queries
            ai_response = await get_openai_response(message, include_schema=is_transaction_query(message))
            
            # Try to extract SQL query if it exists in the response
            sql_query = extract_sql_query(ai_response)
            
            if sql_query:
                try:
                    # Execute the extracted SQL query
                    result = execute_sql_query(sql_query)
                    viz_type = determine_visualization_type(sql_query, result)
                    formatted_result = format_query_response(result, viz_type)
                    
                    # Combine AI explanation with formatted result
                    response = {
                        "type": "combined",
                        "explanation": ai_response,
                        "data": formatted_result
                    }
                    return jsonify(response)
                except Exception as e:
                    error_msg = str(e)
                    if "Database error" in error_msg:
                        return jsonify({
                            "type": "error", 
                            "content": f"{ai_response}\n\nDatabase error: {error_msg.split('Database error: ')[-1]}"
                        })
                    return jsonify({
                        "type": "error", 
                        "content": f"{ai_response}\n\nError executing the generated query: {error_msg}"
                    })
            else:
                # If no SQL query was found, just return the AI response
                return jsonify({"type": "text", "content": ai_response})
                
        except Exception as e:
            return jsonify({
                "type": "error", 
                "content": f"Error processing your request: {str(e)}"
            })
            
    except Exception as e:
        return jsonify({
            "type": "error", 
            "content": f"Unexpected error: {str(e)}"
        }), 500

if __name__ == '__main__':
    print("Starting Flask development server...")
    app.run(host='127.0.0.1', port=8080, debug=True) 