import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from urllib.parse import quote_plus
import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# Load environment variables from .env file
load_dotenv()

def get_full_chain():
    """
    Initializes all components and returns the full LangChain SQL chain.
    """
    # LLM setup
    llm = ChatOpenAI(
        model_name="llama-33-70b", 
        base_url=os.getenv("BASE_URL"),
        api_key="-",
        temperature=0.1
    )

    # Database Setup
    password = os.getenv("DB_PASSWORD")
    encoded_password = quote_plus(password)
    db_uri = f"mysql+mysqlconnector://root:{encoded_password}@localhost:3306/chatbot_berufungsverfahren"
    # Connect without include_tables first
    db = SQLDatabase.from_uri(
        db_uri, 
        schema="chatbot_berufungsverfahren"
    )
    
    # Get schema info for your specific table and view
    job_positions_info = db.get_table_info_no_throw(['job_positions'])
    full_procedure_info = db.get_table_info_no_throw(['full_procedure_view'])
    
    # Create a new database connection with custom table info
    db = SQLDatabase.from_uri(
        db_uri,
        schema="chatbot_berufungsverfahren",
        custom_table_info={'job_positions': job_positions_info, 'full_procedure_view': full_procedure_info}
    )

    print("Available tables/views:")
    print(db.get_usable_table_names())

    def get_schema(_):
        return db.get_table_info()

    # Function to safely run query
    def safe_run_query(sql: str):
        try:
            # We don't need to extract SQL again if the LLM is only returning the query
            return db.run(sql)
        except Exception as e:
            return f"SQL Execution Failed:\nQuery: {sql}\nError: {str(e)}"

    # Prompt template to generate the SQL query
    sql_prompt = ChatPromptTemplate.from_template(
        """
        Based on the table schema below, write a SQL query that would answer the user's question.
        Schema:
        {schema}

        Question:
        {question}

        Only return the raw SQL query. Do not include explanation or markdown formatting like ```sql.
        """
    )

    # Prompt template to generate the final natural language response
    final_response_prompt = ChatPromptTemplate.from_template(
        """
        Based on the table schema, question, SQL query, and SQL response, write a natural language response.

        Schema:
        {schema}

        Question:
        {question}

        SQL Query:
        {query}

        SQL Response:
        {response}
        """
    )

    # Define Chains
    sql_chain = (
        RunnablePassthrough.assign(schema=get_schema)
        | sql_prompt
        | llm.bind(stop="\nSQL Result:")
        | StrOutputParser()
    )

    full_chain = (
        RunnablePassthrough.assign(query=sql_chain).assign(
            schema=get_schema,
            response=lambda vars: safe_run_query(vars["query"])
        )
        | final_response_prompt
        | llm
        | StrOutputParser()
    )

    return full_chain