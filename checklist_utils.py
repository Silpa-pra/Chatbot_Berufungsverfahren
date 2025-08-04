from typing import Dict, Any, cast
from db_utils import get_db_cursor
import os
from datetime import datetime

def get_all_positions(user_id= None, user_type = None):
    """
    Fetches job positions based on user role.
    HR sees all positions, BA only sees assigned positions
    """
    with get_db_cursor() as (conn, cursor):
        if user_type == "HR":
            cursor.execute("""
                SELECT jp.position_id, jp.position_title, jp.kenziffer, jp.department,
                       ba.ba_name, bm.is_head  
                FROM job_positions jp
                LEFT JOIN berufungsausschuss ba ON jp.ba_id = ba.ba_id
                LEFT JOIN ba_members bm ON ba.ba_id = bm.ba_id
                WHERE jp.status IN ('created', 'in_progress')
            """)
        else:
            cursor.execute("""
                SELECT jp.position_id, jp.position_title, jp.kenziffer, jp.department,
                       ba.ba_name, bm.is_head  
                FROM job_positions jp
                JOIN ba_members bm ON jp.ba_id = bm.ba_id
                JOIN berufungsausschuss ba ON jp.ba_id = ba.ba_id
                WHERE bm.user_id = %s AND jp.status IN ('created', 'in_progress')
            """, (user_id,))  
             
        return cursor.fetchall()
    
def get_full_procedure_data(user_id: int, position_id: int):
    """
    Get comprehensive status information including current step & all related data.
    Returns everything needed for both chatbot response & interactive checklist. 
    """
    
    with get_db_cursor() as (conn, cursor):
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
                'step_link': task['step_link'],
                'tasks': []
            }
        
        task_dict = {
            'task_id' : task.get('task_id'),
            'task_description': task.get('task_description'),
            'task_order': task.get('task_order'),
            'required_documents': task.get('required_documents'),
            'task_link': task.get('task_link'),
            'task_status': task.get('task_status', 'not_started'),
            'completed_at': task.get('completed_at'),
            'notes': task.get('notes')
            }
            
        all_steps[step_id]['tasks'].append(task_dict)
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
    with get_db_cursor() as (conn, cursor):
        query = """
        INSERT INTO user_progress (user_id, position_id, task_id, status, completed_at)
        VALUES (%s, %s, %s, %s, CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END)
        ON DUPLICATE KEY UPDATE status = VALUES(status), 
        completed_at = VALUES(completed_at);
        """ 
        cursor.execute(query, (user_id, position_id, task_id, new_status, new_status))
        conn.commit()
        return True
   
        
def create_chat_session(user_id, position_id):
    """
    Creates a new chat session record for tracking conversation history.
    
    param:
        user_id(int): The ID of the user starting the chat
        position_id(int): The ID of job position being discussed
        
    return:
    int: The auto generated session_id for the new session.
    """
    
    with get_db_cursor() as (conn, cursor):
        cursor.execute("""
                       INSERT INTO chat_sessions(user_id, position_id)
                       VALUES(%s, %s)""", (user_id, position_id))
        conn.commit()
        return cursor.lastrowid
   

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
    with get_db_cursor() as (conn, cursor):
        cursor.execute("""
                       INSERT INTO chat_messages(session_id, sender_type, message_text)
                       VALUES (%s, %s, %s)""", (session_id, sender_type, message_text))
        conn.commit()
    
        
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
    with get_db_cursor() as (conn, cursor):
        cursor.execute("""
                       SELECT cm.sender_type, cm.message_text, cm.created_at
                       FROM chat_sessions cs
                       JOIN chat_messages cm ON cs.session_id = cm.session_id
                       WHERE cs.user_id = %s and cs.position_id = %s
                       ORDER BY cm.created_at DESC
                       LIMIT %s""", (user_id, position_id, limit))
        return cursor.fetchall()
    

def initialize_shared_progress(position_id):
    """ Inititalize shared progress for a position when first accessed"""
       
    try:
        with get_db_cursor() as (conn,cursor):
            # check if records already exist
            cursor.execute("""
                           SELECT COUNT(*) as count FROM ba_shared_progress
                           WHERE position_id = %s
                           """, (position_id,))
            
            result = cursor.fetchone()
            if result and result.get('count', 0) > 0:
                return True  # Already initialized
            
            # Get ba_id and all tasks for this position
            cursor.execute("""
                           SELECT jp.ba_id, st.task_id
                           FROM job_positions jp
                           JOIN procedures p ON jp.procedure_id = p.procedure_id
                           JOIN procedure_phases ph ON p.procedure_id = ph.procedure_id
                           JOIN procedure_steps ps ON ph.phase_id = ps.phase_id
                           JOIN step_tasks st ON ps.step_id = st.step_id
                           WHERE jp.position_id = %s
                           """, (position_id,))
        
        results = cursor.fetchall()
        if not results:
            return False
            
        ba_id = results[0].get('ba_id')
        
        # Insert initial records for all tasks
        for row in results:
            task_id = row.get('task_id')
            cursor.execute("""
                INSERT IGNORE INTO ba_shared_progress (position_id, task_id, ba_id, status)
                VALUES (%s, %s, %s, 'not_started')
            """, (position_id, task_id, ba_id))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error initializing shared progress: {e}")
        return False
    
def get_shared_procedure_data(position_id):
    """ Get procedure data with shared progress """
    
    initialize_shared_progress(position_id)
    
    try:
        with get_db_cursor() as (conn, cursor):
            query = """
            SELECT p.procedure_title,
                p.grundlage,
                ph.phase_id,
                ph.phase_title,
                ph.phase_order,
                ph.link_url as phase_link,
                ps.step_id,
                ps.step_title,
                ps.step_order,
                ps.link_url as step_link,
                st.task_id,
                st.task_description,
                st.task_order,
                st.required_documents,
                st.link_url as task_link,
                COALESCE(bsp.status, 'not_started') as task_status,
                bsp.completed_at,
                bsp.notes
            FROM job_positions jp
            JOIN procedures p ON jp.procedure_id = p.procedure_id
            JOIN procedure_phases ph ON p.procedure_id = ph.procedure_id
            JOIN procedure_steps ps ON ph.phase_id = ps.phase_id
            JOIN step_tasks st ON ps.step_id = st.step_id
            LEFT JOIN ba_shared_progress bsp ON st.task_id = bsp.task_id AND bsp.position_id = jp.position_id
            LEFT JOIN users u ON bsp.completed_by_user_id = u.user_id  
            WHERE jp.position_id = %s 
            ORDER BY ph.phase_order, ps.step_order, st.task_order 
            """
            
            cursor.execute(query,(position_id,))
            all_tasks = cursor.fetchall()
            
            if not all_tasks:
                return None
            
            return analyze_user_progress(all_tasks)
        
    except Exception as e:
        print(f"Error getting shared procedure data:{e}")
        return None

def update_shared_task_status(position_id, task_id, new_status, user_id, username, notes= None):
    """ Update shared task status"""
    
    try:
        with get_db_cursor() as (conn, cursor):
            # get the ba_id for this position
            cursor.execute("""
                           SELECT ba_id FROM job_positions WHERE position_id = %s
                           """, (position_id,))
            result = cursor.fetchone()
            if not result:
                print(f"No job position found for position_id:{position_id}")
                return False
            
            ba_id = result.get('ba_id')
            
            query = """
            INSERT INTO ba_shared_progress(position_id, task_id, ba_id, status, completed_by_user_id, notes, completed_at)
            VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END)
            ON DUPLICATE KEY UPDATE 
            status = VALUES(status),
            completed_by_user_id = VALUES(completed_by_user_id),
            notes = VALUES(notes),
            completed_at = VALUES(completed_at)
            """
            cursor.execute(query, (position_id, task_id, ba_id, new_status, user_id, notes, new_status))
                
            cursor.execute("""
            INSERT INTO user_progress (user_id, position_id, task_id, status, notes, completed_at)
            VALUES (%s, %s, %s, %s, %s, CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END)
            ON DUPLICATE KEY UPDATE 
            status = VALUES(status), 
            notes = VALUES(notes),
            completed_at = VALUES(completed_at)
            """,(user_id, position_id, task_id, new_status, notes, new_status) )
            
            conn.commit()
            
            if cursor.rowcount == 0:
                print(f"No rows affected when updating task{task_id} for position {position_id}")
                return False
            return True
        
    except Exception as e:
        print(f"Error updating shared task status:{e}")
        return False


    
def save_document_upload(user_id, position_id, task_id, uploaded_file):
    """
    Save uploaded .txt document to file system and record in database
    
    Args:
        user_ID: ID of user uploading the document
        position_id: Id of the position
        task_id : Id of the task requiring the document
        uploaded_file: Streamlit UploadeddFile object
    Returns:
        bool: True if successful, otherwise False 
        
    """
    try:
        upload_dir = os.path.join("uploads", str(position_id), str(task_id))
        os.makedirs(upload_dir, exist_ok = True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{uploaded_file.name}"
        file_path = os.path.join(upload_dir, filename)
        
        # Save file to disk
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        # Save record to database
        with get_db_cursor() as (conn, cursor):
            cursor.execute("""
                           INSERT INTO document_uploads(
                               user_id, position_id, task_id, original_filename, file_path)
                               VALUES(%s, %s, %s, %s, %s)
                            """, (user_id, position_id, task_id, uploaded_file.name, file_path))
            conn.commit()
            return True  
    
    except Exception as e:
        print(f"Error saving document: {e}")
        return False

def get_uploaded_document(task_id, position_id):
    """
    Get information about uploaded document for a task
    
    Args:
        task_id: Id of the task
        position_id : Id of the position
        
    Returns:
        dict: Document information or None if not found
    """
    
    try:
        with get_db_cursor()  as (conn, cursor):
            cursor.execute("""
                           SELECT du.upload_id,
                           du.original_filename,
                           du.file_path,
                           u.username
                           FROM document_uploads du
                           JOIN users u ON du.user_id = u.user_id
                           WHERE du.task_id = %s AND du.position_id = %s
                           ORDER BY du.upload_id DESC
                           LIMIT 1
                           """, (task_id, position_id))
            return cursor.fetchone()
    except Exception as e:
        print(f"Error getting document:{e}")
        return None

def read_uploaded_document(task_id, position_id):
    """
    Read the content of an uploaded document
    
    Args:
        task_id: Id of the task
        position_id: Id of the position
        
    Returns:
        str: File content or None if not found/error
    """
    try:
        doc_info = get_uploaded_document(task_id,position_id)
        if doc_info and doc_info.get('file_path'):
            with open(doc_info['file_path'], 'r', encoding = 'utf-8') as f:
                return f.read()
            return None
    except Exception as e:
        print(f"Error reading document:{e}")
        return None
    
def delete_uploaded_doc(task_id, position_id):
    try:
        with get_db_cursor() as (conn, cursor):
            # get file path
            cursor.execute("""
                           SELECT file_path FROM document_uploads
                           WHERE task_id = %s AND position_id = %s 
                           """, (task_id, position_id))
            row = cursor.fetchone()
            
            if row:
                file_path = row['file_path']
                
                # delete file 
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
                # delete db record
                cursor.execute("""
                               DELETE FROM document_uploads
                               WHERE task_id=%s AND position_id = %s
                               """, (task_id, position_id))
                conn.commit()
                return True
            return False
    except Exception as e:
        print(f"Error deleting document:{e}")
        return False
                
                