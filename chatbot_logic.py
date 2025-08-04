import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from urllib.parse import quote_plus
import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser
from langchain_core.runnables import RunnablePassthrough
from typing  import List

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
    db_uri = f"mysql+mysqlconnector://root:{encoded_password}@localhost:3306/berufungsverfahren_chatbot"
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

def get_profile_suggestion(profile_content: str) -> dict:
    """ 
    Get AI suggestions for improvising a requirement profile 
    
    Args:
        file_content : The text content of the requirement profile
    
    Returns:
        dict: Suggestions and improved version
    
    """
    
    llm = ChatOpenAI(
        model ="llama-33-70b",
        base_url = os.getenv("BASE_URL"),
        temperature= 0.2
    )
    
    # Good example for reference
    good_example = """Professor for Data Science and Machine Learning (W3)
    University of Excellence

    Position Overview:
    The Faculty of Computer Science seeks an outstanding scholar for a tenured full professor position in Data Science and Machine Learning, focusing on applied research and industry collaboration.

    Academic Qualifications:
    - PhD in Computer Science, Data Science, Statistics, or related field
    - Habilitation or equivalent international qualification
    - Strong publication record in top venues (NeurIPS, ICML, KDD, JMLR)
    - H-index of at least 20

    Professional Experience:
    - Minimum 5 years post-doctoral experience
    - Track record of securing research funding (€500k+ as PI)
    - Experience supervising PhD students (3+ completions)
    - Industry collaboration experience
    - International research network

    Research Expectations:
    - Lead internationally visible research group
    - Publish 3-5 high-impact papers annually
    - Secure €200k+ external funding per year
    - Supervise 3-5 PhD students
    - Foster interdisciplinary collaborations

    Teaching Responsibilities:
    - 9 SWS teaching load including:
    - Undergraduate: Intro to ML, Data Mining
    - Graduate: Deep Learning, Statistical Learning
    - Develop new courses in emerging areas
    - Supervise 10-15 Master theses annually
    - Engage in curriculum development

    Required Skills:
    - ML frameworks expertise (TensorFlow, PyTorch)
    - Python, R proficiency
    - Cloud computing experience
    - Strong communication and leadership
    - English fluency (mandatory)
    - German B2 within 2 years (support provided)

    Equal Opportunity:
    The university values diversity and encourages applications from underrepresented groups. Family-friendly policies and dual career support available."""

    # Poor example for contrast
    poor_example = """Professor Position

    Need professor for computer science.

    Requirements:
    - PhD
    - Teaching experience 
    - Programming proficiency
    - Research
    - English

    Salary negotiable.
    """
    
    # check if the profile is already good enough
    profile_check = profile_content.lower()
    required_sections =[ "position overview", "academic qualifications", "professional experience", 
                        "research expectation", "teaching responsibilities","required skills"]
    
    #count how many required sections are present
    sections_present = sum( 1 for section in required_sections if section in profile_check)
    
    
    # if profile has most sections and long enough, return positive feedback
    if sections_present >= 5 and len(profile_content)>520:
        suggestion_prompt = ChatPromptTemplate.from_template(
            """You are an expert HR consultant. This requirement profile is already well structured but review it for potential refinement and optimizations.
            
            REQUIREMENT PROFILE:
            {profile_content}
            
            This is a well-structured profile. Provide encouragement and subtle improvements.
        
            Start your response by acknowledging their good work, then provide:

            SUGGESTIONS:
            - Great job! Your profile is comprehensive and professional
            - You can upload this document as-is, or consider these minor enhancements:
            [List 3-4 minor improvement suggestions]

            MISSING ELEMENTS:
            [List any minor elements that could enhance the profile]

            IMPROVED VERSION:
            [Provide a polished, enhanced version with your refinements]      
            
            """
        )
     
    else:
         suggestion_prompt = ChatPromptTemplate.from_template(
            """You are an expert HR consultant. Review this requirement profile and provide helpful suggestions.
            REQUIREMENT PROFILE:
            {profile_content}
        
            Compare it with this GOOD EXAMPLE structure:
            {good_example}
        
        
            This profile needs significant improvement. Focus on:
            1. Adding missing essential sections
            2. Providing more specific requirements
            3. Improving structure and clarity
            4. Adding professional details

            Respond using the format below:

            SUGGESTIONS:
            [List suggestions here]

            MISSING ELEMENTS:
            [List missing things]

            IMPROVED VERSION:
            [Improved version here]
            """
        )
    
    try: 
        # send prompt to llm
        chain = suggestion_prompt| llm | StrOutputParser()
        result = chain.invoke({
            "profile_content": profile_content,
            "good_example": good_example,
            "poor_example": poor_example
        })
        
        # just split by keywords
        sections = result.split("IMPROVED VERSION:")
        
        if len(sections) == 2:
            # We found the improved version
            first_part = sections[0]
            improved_version = sections[1].strip()
            
            # Try to get suggestions and missing elements
            suggestions = ["Review and enhance the profile structure",
                          "Add more specific requirements",
                          "Include clear expectations"]
            missing = ["Some sections may need more detail"]
            
            # Simple extraction attempt
            if "SUGGESTIONS:" in first_part and "MISSING ELEMENTS:" in first_part:
                try:
                    sug_text = first_part.split("SUGGESTIONS:")[1].split("MISSING ELEMENTS:")[0]
                    miss_text = first_part.split("MISSING ELEMENTS:")[1]
                    
                    # Get first 3-5 non-empty lines as suggestions
                    sug_lines = [line.strip() for line in sug_text.strip().split('\n') if line.strip()]
                    miss_lines = [line.strip() for line in miss_text.strip().split('\n') if line.strip()]
                    
                                  
                    if sug_lines:
                        suggestions = sug_lines[:5]
                    if miss_lines:
                        missing = miss_lines[:5]
                except Exception as e:
                    print(f"Extraction error: {e} ")
                    
            
            return {
                "status": "success",
                "suggestions": suggestions,
                "missing_elements": missing,
                "improved_version": improved_version,
                "message": None
            }
        else:
            # Couldn't parse properly, return the whole response
            return {
                "status": "success",
                "suggestions": ["Please review the AI suggestions below"],
                "missing_elements": [],
                "improved_version": result,
                "message": None
            }
            
    except Exception as e:
        print(f"Error getting suggestions: {e}")
        return {
            "status": "error",
            "suggestions": [f"Error: {str(e)}"],
            "missing_elements": [],
            "improved_version": None
        }
        
def detect_current_task_question(user_input):
    """
    Detect if user is asking specifically about their current task
    """
    current_task_phrases=[
        'what is my current task',
        'what task am i on',
        'what\'s my current task',
        'what is the current task',
        'current task is'
    ]
    
    user_input_lower = user_input.lower()
    return any(phrase in user_input_lower for phrase in current_task_phrases)


def detect_status_question(user_input: str):
    """
    Detects if usesr is asking about their status or progress
    """
    possible_keywords =[
        'status',  'progress', 'next', 'step', 'task', 'completed', 'done',
        'where am i', 'current', 'phase', 'what do i need', 'what should i do',
        'what\'s next', 'overview', 'todo', 'procedure', 'checklist',
        'tasks', 'remaining', 'pending', 'finished'
    ]
    
    return any(keyword in user_input.lower() for keyword in possible_keywords)

def detect_task_help_request(user_input:str):
    """
    Detect if user is asking for help with task
    """
    help_keywords = [
        'help me with', 'explain', 'simplify', 'what does this mean',
        'help with task', 'help with current', 'break down', 'clarify',
        "don't understand", 'confused about', 'guide me', 'assist with', 'help me understand', 'what to do'
    ]
    
    user_input_lower = user_input.lower()
    
    return any(keyword in user_input_lower for keyword in help_keywords)



def generate_task_response(status_data, response_type="status", user_input=""):
    """
    Unified generator for all task-related responses
    
    Args:
        status_data: The current status data
        response_type: "status" | "current_task" | "task_help"
        user_input: Original user input (for context)
    """
    if not status_data or not status_data.get('current_step'):
        return "I couldn't find any procedure data for this job position."
    
    current_step = status_data['current_step']
    progress = status_data.get('progress', {})
    
    if response_type == "status":
        # Full status overview
        procedure_title = status_data['procedure_info']['procedure_title']
        response = f"### Current Status: {procedure_title}\n\n"
        response += f"**You are currently in:**\n"
        response += f" {current_step['phase_title']}\n"
        response += f"Step: {current_step['step_title']}\n\n"
        response += f"**Progress:**\n"
        response += f"Overall: {progress['completed_tasks']}/{progress['total_tasks']} tasks ({progress['percentage']:.1f}%)\n"
        response += f"Current step: {progress['current_step_completed']}/{progress['current_step_total']} tasks ({progress['current_step_percentage']:.1f}%)\n\n"
        
        if progress['current_step_completed'] == progress['current_step_total']:
            response += "**This step is completed!** You can proceed to next step.\n\n"
        else:
            remaining = progress['current_step_total'] - progress['current_step_completed']
            response += f"**{remaining} tasks remaining in this step.**\n\n"
        
        response += "**Use the checklist on the right to mark tasks as completed.**"
        return response
    
    elif response_type == "current_task":
        # Current task only
        incomplete_tasks = [t for t in current_step['tasks'] if t['task_status'] != 'completed']
        
        if incomplete_tasks:
            current_task = incomplete_tasks[0]
            response = f"Your current task is:\n\n**{current_task['task_description']}**"
            if current_task.get('required_documents'):
                response += f"\n\nRequired documents: {current_task['required_documents']}"
            response += "\n\nYou can mark this as completed in the checklist on the right when you are done."
        else:
            response = "All tasks in the current step are completed! The procedure will move on to the next step."
        return response
    
    
    elif response_type == "task_help":
        # Simplified task explanation (calls existing chain)
        incomplete_tasks = [t for t in current_step['tasks'] if t['task_status'] != 'completed']
        if incomplete_tasks:
            current_task = incomplete_tasks[0]
            simplification_chain = get_task_simplification_chain()
            return simplification_chain.invoke({
                "task_description": current_task.get('task_description'),
                "required_documents": current_task.get('required_documents') or "None specified",
                "step_title": current_step.get('step_title'),
                "phase_title": current_step.get('phase_title')
            })
        else:
            return "All tasks are completed in this step!"
    
    return "I couldn't understand what information you need. Try asking about your status, current task, or next task."