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
    Initializes and returns the complete LangChain SQL chain for the chatbot.
    This chain can answer questions about procedures, steps, and requirements.
    
    """
    # LLM setup
    llm = ChatOpenAI(
        model="llama-33-70b", 
        base_url=os.getenv("BASE_URL"),
        temperature=0.1
    )

    # Database Setup
    password = os.getenv("DB_PASSWORD")
    if password is None:
        raise ValueError("Environment  variable DB_PASSWORD is not set.")
    
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
        """
        Returns the database schema information for the LLM to understand table structure.
        """
        return db.get_table_info()

    # Function to safely run query
    def safe_run_query(sql: str):
        """
        Safely executes SQL queries with error handling.
        Returns the result or an error message if the query fails.
        """
        try:
            # no need to extract SQL again if the LLM is only returning the query
            return db.run(sql)
        except Exception as e:
            return f"SQL Execution Failed:\nQuery: {sql}\nError: {str(e)}"

    # Prompt template to generate the SQL query
    sql_prompt = ChatPromptTemplate.from_template(
        """
        You are a SQL expert. Based on the table schema below, write a SQL query that would answer the user's question.
        Schema:
        {schema}

        Question:
        {question}
        
        Important guidelines:
        - Only return the raw SQL query. Do not include explanation or markdown formatting like ```sql.
        - Focus on procedures, phases, steps, tasks and user progress
        - Use JOINS appropriately to get complete information
        - For progress queries, include user_progress table
        - For procedure questions, focus on procedures, procedure_phases, procedure_steps, and step_tasks tables
        - The database may contain German content
        
        SQL Query:
        """
    )

    # Prompt template to generate the final natural language response
    final_response_prompt = ChatPromptTemplate.from_template(
        """
        Based on the database schema, user question, SQL query, and SQL response, write a natural language response.

        Schema:
        {schema}

        Question:
        {question}

        SQL Query:
        {query}

        SQL Response:
        {response}
        
        Guidelines for your response:
        -Be conversational and helpful
        -If results show procedure steps, explain them clearly
        -If no results found, suggest what the user might try instead 
        -Use bullet poinsts or numbered lists for clarity when appropriate
        -focus on actionable information
        -Maintain consistency in the response language throughout
        """
    )
    
    # Chain Definition
    # First Chain:Generate SQL query from natural language question
    sql_chain = (
        RunnablePassthrough.assign(schema=get_schema)
        | sql_prompt
        | llm.bind(stop="\nSQL Result:")
        | StrOutputParser()
    )
    
    # Full chain: Generate SQL, execute it, then create natural language response
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

def get_task_simplification_chain():
    """
    Create a chain specifically for simplifying task explanations
    """
    
    llm = ChatOpenAI(
        model = "llama-33-70b",
        base_url = os.getenv("BASE_URL"),
        api_key= "-",
        temperature =0.0        
    )
    
    simplification_prompt = ChatPromptTemplate.from_template(
        """
        You are a helpful assistant that simplifies complex hiring procedure tasks.
        
        Task Information:
        Task Description: {task_description}
        Required Documents: {required_documents}
        Current Step: {step_title}
        Current Phase: {phase_title}

        Please provide a simplified, user-friendly explanation of this task.
        
        Your explanation should:
        1. Break down what needs to be done in simple steps
        2. Explain any technical terms in plain language
        3. Clarify what documents are needed and why
        4. Provide practical tips or suggestions
        5. Be encouraging and supportive
        
        Simplified explanation:
        """
    )
    chain = simplification_prompt | llm | StrOutputParser()
        
    return chain