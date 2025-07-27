from typing import Dict, Any, cast
from db_utils import get_db_connection

def get_all_positions(user_id= None, user_type = None):
    """
    Fetches job positions based on user role.
    HR sees all positions, BA only sees assigned positions
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if user_type == "HR":
            cursor.execute("""
                SELECT jp.position_id, jp.position_title, jp.kenziffer, jp.department,
                       ba.ba_name, bm.is_head  -- ← Make sure ba_name is selected
                FROM job_positions jp
                LEFT JOIN berufungsausschuss ba ON jp.ba_id = ba.ba_id
                LEFT JOIN ba_members bm ON ba.ba_id = bm.ba_id
                WHERE jp.status IN ('created', 'in_progress')
            """)
        else:
            cursor.execute("""
                SELECT jp.position_id, jp.position_title, jp.kenziffer, jp.department,
                       ba.ba_name, bm.is_head  -- ← Make sure ba_name is selected
                FROM job_positions jp
                JOIN ba_members bm ON jp.ba_id = bm.ba_id
                JOIN berufungsausschuss ba ON jp.ba_id = ba.ba_id
                WHERE bm.user_id = %s AND jp.status IN ('created', 'in_progress')
            """, (user_id,))  
             
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []
    finally:
        cursor.close()
        conn.close()
        
def get_full_procedure_data(user_id: int, position_id: int):
    """
    Get comprehensive status information including current step & all related data.
    Returns everything needed for both chatbot response & interactive checklist. 
    """
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # get all tasks with their progress for this position
        query = """
            SELECT
                p.procedure_title,
                p.grundlage,
                ph.phase_id,
                ph.phase_title,
                ph.phase_order,
                ph.link_url as phase_link,
                ps.step_id,
                ps.step_title,
                ps.step_order,
                ps.responsible_user_type,
                ps.link_url as step_link,
                st.task_id,
                st.task_description,
                st.task_order,
                st.required_documents,
                st.link_url as task_link,
                COALESCE(up.status, 'not_started') as task_status,
                up.completed_at
                FROM job_positions jp
                JOIN procedures p ON jp.procedure_id = p.procedure_id
                JOIN procedure_phases ph ON p.procedure_id = ph.procedure_id
                JOIN procedure_steps ps ON ph.phase_id = ps.phase_id
                JOIN step_tasks st ON ps.step_id = st.step_id
                LEFT JOIN user_progress up ON st.task_id = up.task_id
                AND up.position_id = jp.position_id
                AND up.user_id = %s
                WHERE jp.position_id = %s 
                ORDER BY ph.phase_order, ps.step_order, st.task_order        
        """ 
        
        cursor.execute(query, (user_id, position_id))  
        all_tasks = cursor.fetchall()
        
        if not all_tasks:
            return None
        
        #Analyze the data to get comprehensive status
        status_data = analyze_user_progress(all_tasks) 
        
        return status_data
    
    except Exception as e:
        print(f"Error getting comprehensive user status:{e}")
        return None
    finally:
        cursor.close()
        conn.close()
        

def analyze_user_progress(all_tasks):
    """
    Analyzes all tasks to provide comprehensive progress information.
    Returns structured data for  both chatbot and UI components.
    """
    
    if not all_tasks:
        return None
    
    #Basic procedure info
    procedure_info ={
        'procedure_title': all_tasks[0]['procedure_title'],
        'grundlage': all_tasks[0]['grundlage']
    }
    
    # Group tasks by steps and phases
    phases ={}
    all_steps ={}
    
    for task in all_tasks:
        phase_id = task['phase_id']
        step_id = task['step_id']
        
        #Group by phases
        if phase_id not in phases:
            phases[phase_id] = {
                'phase_title': task['phase_title'],
                'phase_order': task['phase_order'],
                'phase_link': task['phase_link'],
                'steps': {}
            }
        
        #Group by steps
        if step_id not in all_steps:
            all_steps[step_id] = {
                'step_id': step_id,
                'phase_title': task['phase_title'],
                'phase_order': task['phase_order'],
                'step_title': task['step_title'],
                'step_order': task['step_order'],
                'responsible_user_type': task['responsible_user_type'],
                'step_link': task['step_link'],
                'tasks': []
            }
            
        all_steps[step_id]['tasks'].append(task)
        phases[phase_id]['steps'][step_id] = all_steps[step_id]
        
    
    #Find current step(first step with incomplete tasks)
    sorted_steps = sorted(all_steps.values(), key=lambda x: (x['phase_order'], x['step_order']))
    current_step = None
    
    for step in sorted_steps:
        incomplete_tasks = [t for t in step['tasks'] if t['task_status'] != 'completed']
        if incomplete_tasks:
            current_step = step
            break
        
    # If no incomplete steps, take the last step
    if not current_step and sorted_steps:
        current_step = sorted_steps[-1]
        
    # Calculate progress statics
    total_tasks = len(all_tasks)
    completed_tasks = len([t for t in all_tasks if t['task_status']=='completed'])
    overall_percentage = (completed_tasks/total_tasks*100) if total_tasks > 0 else 0
    
    #Calculate current step progress
    current_step_completed = 0
    current_step_total = 0
    current_step_percentage= 0
    
    if current_step:
        current_step_total = len(current_step['tasks'])
        current_step_completed= len([t for t in current_step['tasks'] if t['task_status'] == 'completed'])
        current_step_percentage = (current_step_completed / current_step_total * 100) if current_step_total > 0 else 0
        
    #create progress dictionary
    progress ={'total_tasks': total_tasks,
               'completed_tasks': completed_tasks,
               'percentage': overall_percentage,
               'current_step_total': current_step_total,
               'current_step_completed': current_step_completed,
               'current_step_percentage': current_step_percentage
               } 
    
        
    return{
        'procedure_info' : procedure_info,
        'current_step' : current_step,
        'all_phases' : phases,
        'all_steps' : sorted_steps,
        'progress' : progress
    }
            


def update_task_status(user_id: int, position_id: int, task_id: int, new_status: str):
    """
    Update the status of a specific task for a user
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        INSERT INTO user_progress (user_id, position_id, task_id, status, completed_at)
        VALUES (%s, %s, %s, %s, CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END)
        ON DUPLICATE KEY UPDATE 
            status = VALUES(status), 
            completed_at = VALUES(completed_at);
    """
    try:
        cursor.execute(query, (user_id, position_id, task_id, new_status, new_status))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating task status: {e}")
        return False
    finally:
        cursor.close()
        conn.close()
        
def create_chat_session(user_id, position_id):
    """
    Creates a new chat session record for tracking conversation history.
    
    param:
        user_id(int): The ID of the user starting the chat
        position_id(int): The ID of job position being discussed
        
    return:
    int: The auto generated session_id for the new session.
    """
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
                       INSERT INTO chat_sessions(user_id, position_id)
                       VALUES(%s, %s)""", (user_id, position_id))
        conn.commit()
        return cursor.lastrowid
    finally: 
        cursor.close()
        conn.close()

def save_chat_message(session_id, sender_type, message_text):
    """
    Sasves a chat message to the database for persistance and audit purpose.
    
    param:
        session_id(int): The ID of the active chat session
        sender_type(str): Origin of message - 'user' or 'bot'
        message_text(str): The message content to store
        
    return:
        None
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
                       INSERT INTO chat_messages(session_id, sender_type, message_text)
                       VALUES (%s, %s, %s)""", (session_id, sender_type, message_text))
        conn.commit()
    finally:
        cursor.close()
        conn.close()
        
def get_chat_history(user_id, position_id, limit=50):
    """
    Retreives previous chat messages for a user and position to restore context.
    
    param:
        user_id(int): The ID of the user whose history to retrieve
        position_id(int): The ID  of the job postion to filter by 
        limit(int): Maximum messages to return(default: 50)
        
    return:
        list[dict]: messages with sender_type, message_text, created_at.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
                       SELECT cm.sender_type, cm.message_text, cm.created_at
                       FROM chat_sessions cs
                       JOIN chat_messages cm ON cs.session_id = cm.session_id
                       WHERE cs.user_id = %s and cs.position_id = %s
                       ORDER BY cm.created_at DESC
                       LIMIT %s""", (user_id, position_id, limit))
        return cursor.fetchall()
    finally:
        conn.close()
        cursor.close()
        
def get_next_step_preview(status_data, num_steps: int = 2):
    """
    Gets a Preview  of the next few steps.
    """
    if not status_data or not status_data['current_step']:
        return[]
    
    current_step_id = status_data['current_step']['step_id']
    all_steps = status_data['all_steps']
    
    #Find current step index
    current_index = None
    for i, step in enumerate(all_steps):
        if step['step_id']== current_step_id:
            current_index = 1
            break
        
        if current_index is None:
            return[]
        
        #Get next steps
        next_steps = []
        for i in range(current_index +1, min(current_index+1+num_steps, len(all_steps))):
            next_steps.append(all_steps[i])
            
        return next_steps

def detect_status_question(user_input: str):
    """
    Detects 
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
    Detect
    """
    help_keywords = [
        'help me with', 'explain', 'simplify', 'what does this mean',
        'help with task', 'help with current', 'break down', 'clarify',
        "don't understand", 'confused about', 'guide me', 'assist with', 'help me understand'
    ]
    
    user_input_lower = user_input.lower()
    
    return any(keyword in user_input_lower for keyword in help_keywords)

def generate_chatbot_response(status_data):
    """
    Generate
    """
    if not status_data or not status_data['current_step']:
        return "I couldn't find any procedure data for this job position."
    
    current_step = status_data['current_step']
    progress= status_data['progress']
    procedure_title = status_data['procedure_info']['procedure_title']
    
    # Build concise response focused on guidance
    response = f"##Status: {procedure_title}\n\n"
    
    #Current location in process
    response +=f"** You are currently in: **\n"
    response +=f"Phase:{current_step['phase_title']}\n"
    response += f"Step: {current_step['step_title']}\n\n"
    
    #Progress summary
    response += f"** Progress:**\n"
    response += f"Overall: {progress['completed_tasks']}/{progress['total_tasks']} tasks({progress['percentage']:.1f}%)\n"
    response += f"Current step: {progress['current_step_completed']}/{progress['current_step_total']} tasks({progress['current_step_percentage']:.1f}%)\n\n"
    
    
    #Guidance based on current sttus
    if progress['current_step_completed']== progress['current_step_total']:
        response +="**This step is completed!!** You can proceed to next step. \n\n"
    else:
        remaining = progress['current_step_total'] - progress['current_step_completed']
        response+=f"**{remaining} tasks remaining in this step.**\n\n"
        
    #Quick response guidance
    response += "**Use the checklist on the right ot mark tasks as completed.**"
    
    return response



