from db_utils import get_db_connection
from checklist_utils import get_full_procedure_data

# =============================================================================
# JOB POSITION FUNCTIONS
# =============================================================================
def get_active_positions():
    """
    Gets all active positions with BA assignments and progress for Hr dashboard 
    
    return:
        list[dict]: All positions with their BA and progress info.
        """
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        query = """
        SELECT jp.position_id,
        jp.position_title,
        jp.department,
        jp.kenziffer,
        jp.status as position_status,
        ba.ba_id,
        ba.ba_name,
        COUNT(DISTINCT st.task_id) as total_tasks,
        COUNT(DISTINCT CASE WHEN up.status = 'completed' THEN up.task_id END) as completed_tasks
        FROM job_positions jp
        LEFT JOIN berufungsausschuss ba ON jp.ba_id = ba.ba_id
        LEFT JOIN procedure_phases ph ON ph.procedure_id = jp.procedure_id
        LEFT JOIN procedure_steps ps ON ph.phase_id= ps.phase_id
        LEFT JOIN step_tasks st ON ps.step_id = st.step_id
        LEFT JOIN user_progress up ON st.task_id = up.task_id AND up.position_id = jp.position_id
        WHERE jp.status IN ('created', 'in_progress')
        GROUP BY jp.position_id, jp.position_title, jp.department, jp.kenziffer, jp.status, ba.ba_id, ba.ba_name
        ORDER BY  jp.position_id DESC
        """
        
        cursor.execute(query)
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching position:{e}")
        return[]
    finally:
        cursor.close()
        conn.close()
        
def get_position_details(position_id):
    """
    Get detailed information about a specific position for HR view
    param: 
        position_id(int): ID of the position
        
    return:
        dict: Position details including BA info, or None if not found.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        query = """
            SELECT jp.*,
            ba.ba_name,
            ba.ba_id,
            ba.created_at as ba_created_at,
            u.username as created_by_username
            FROM job_positions jp
            LEFT JOIN berufungsausschuss ba ON jp.ba_id = ba.ba_id
            LEFT JOIN users u ON jp.created_by = u.user_id
            WHERE jp.position_id = %s
        """
        cursor.execute(query, (position_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Error fetching position details: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_current_phase_info(position_id, ba_id):
    """
    Gets the current phase and step for a position based on BA progress.
    
    params:
        position_id(int): ID of the position
        ba_id(int): ID of the BA group 
    """
    
    if not ba_id:
        return "No BA assigned", None
    
    # Get any member of the BA to check progress
    members = get_ba_members(ba_id)
    if not members:
        return "BA has no members", None
    
    try: 
        #use the first member's progress as refrence
        status_data = get_full_procedure_data(members[0]['user_id'], position_id)
        if status_data:
            # Find current step based on progress
            for phase_id, phase_data in status_data.items():
                for step_id, step_data in phase_data['steps'].items():
                    # Checks if this step has incomplete tasks
                    incomplete_tasks = [task for task in step_data['tasks']
                                        if task.get('task_status', 'not_started') != 'completed']
                    if incomplete_tasks:
                        return phase_data['phase_title'], step_data['step_title']
                    return "Completed", "All steps finished"
        else:
            return "Not Started", None
    except Exception as e:
        print(f"Error getting current phase info:{e}")
        return "Error", None

def get_position_statistics():
    """
    Gets overall statistics for all postions for HR dashboard
    
    return:
        dict: Statistics including counts and averages
        """
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get position counts
        cursor.execute("""
                       SELECT COUNT(*) as total_positions,
                       COUNT ( CASE WHEN ba_id IS NOT NULL THEN 1 END) as assigned_positions,
                       COUNT(CASE WHEN ba_id IS NULL THEN 1 END) as unassigned_positions,
                       COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_positions
                       FROM job_positions
                       WHERE status IN ('created', 'in_progress', 'completed')
                       """)
        counts = cursor.fetchone()
        
        #Get average progress
        cursor.execute("""
                       SELECT AVG(progress_percentage) as avg_progress
                       FROM (
                       SELECT jp.position_id,
                       CASE
                       WHEN COUNT(st.task_id) = 0 THEN 0
                       ELSE (COUNT(CASE WHEN up.status = 'completed' THEN 1 END) * 100.0 / COUNT(st.task_id))
                       END as progress_percentage
                       FROM job_positions jp
                       LEFT JOIN procedure_phases ph ON ph.procedure_id = jp.procedure_id
                       LEFT JOIN procedure_steps ps ON ph.phase_id = ps.phase_id
                       LEFT JOIN step_tasks st ON ps.step_id = st.step_id
                       LEFT JOIN user_progress up ON st.task_id = up.task_id AND up.position_id = jp.position_id
                       WHERE jp.status IN ('created', 'in_progress')
                       GROUP BY jp.position_id
                       ) as position_progress
                       """)
        avg_result = cursor.fetchone()
        
        return{
            'total_positions': counts['total_positions'],
            'assigned_positions': counts['assigned_positions'],
            'unassigned_positions': counts['unassigned_positions'],
            'completed_positions': counts['completed_positions'],
            'average_progress': avg_result['avg_progress'] or 0
        }
        
    except Exception as e:
        print(f"Error fetching position statistics: {e}")
        return {
            'total_positions': 0,
            'assigned_positions': 0,
            'unassigned_positions': 0,
            'completed_positions': 0,
            'average_progress': 0
        }
    finally:
        cursor.close()
        conn.close()
    
# =============================================================================
# BA COMITTEE FUNCTIONS
# =============================================================================

def create_ba_group(ba_name, created_by_hr_id):
    """
    Creates a new Berufungsausschuss(BA) group
    
    param:
        ba_name(str): Name of the BA group
        created_by_hr_id(int): ID of the HR user creating this BA.
    
    return:
        int: The auto-generated ba_id for the new group, or None if error. 
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(""" INSERT INTO berufungsausschuss(ba_name, created_by)
                       VALUES (%s, %s)
                       """, (ba_name, created_by_hr_id))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error creating BA group:{e}")
        return None
    finally:
        cursor.close()
        conn.close()
    
def add_user_to_ba(ba_id, user_id, is_head= False):
    """
    Adds user to a BA group, optionally as the head.
    
    param:ba_id (int): ID of the BA group.
        user_id (int): ID of the user to add.
        is_head (bool): Whether this user is the BA head.
    
    return:
        bool: True if successful, False otherwise.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # If setting as head, first unset any existing head
        if is_head:
            cursor.execute("""UPDATE ba_members
                           SET is_head = FALSE
                           WHERE ba_id = %s AND is_head = TRUE
                           """, (ba_id,))
            
            cursor.execute("""INSERT INTO ba_members(ba_id, user_id, is_head)
                           VALUES(%s,%s, %s)
                           ON DUPLICATE KEY UPDATE is_head = VALUES(is_head)""", (ba_id, user_id, is_head))
            conn.commit()
            return True
    except Exception as e:
        print(f"Error adding user to BA:{e}")
        return False
    finally:
        cursor.close()
        conn.close()
    
def get_all_ba_groups():
    """
    Gets all BA groups for HR dashboard.
    
    return:
        list[dict]: List of all BA groups with member counts.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
                ba.ba_id,
                ba.ba_name,
                ba.created_at,
                COUNT(DISTINCT bm.user_id) as member_count,
                COUNT(DISTINCT jp.position_id) as position_count
            FROM berufungsausschuss ba
            LEFT JOIN ba_members bm ON ba.ba_id = bm.ba_id
            LEFT JOIN job_positions jp ON ba.ba_id = jp.ba_id
            GROUP BY ba.ba_id
            ORDER BY ba.created_at DESC
        """)
        return cursor.fetchall()
    except Exception as e:
        print(f"Error getting all BA groups: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def get_ba_members(ba_id):
    """Get all members of a specific BA group"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT 
                u.user_id,
                u.username,
                u.email,
                bm.is_head
            FROM ba_members bm
            JOIN users u ON bm.user_id = u.user_id
            WHERE bm.ba_id = %s
            ORDER BY bm.is_head DESC, u.username
        """, (ba_id,))
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching BA members: {e}")
        return []
    finally:
        cursor.close()
        conn.close()
        

def assign_ba_to_position(position_id, ba_id):
    """
    Assign a BA committee to a job position
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
                       UPDATE job_positions
                       SET ba_id = %s
                       WHERE position_id = %s
                       """, (ba_id, position_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error assigning BA : {e}")
        return False
    finally:
        cursor.close()
        conn.close()
        
# =============================================================================
# USER AND POSITION ASSIGNMENT FUNCTIONS
# =============================================================================

def get_available_users_for_ba():
    """
    Gets all USER type users who can be assigned to a BA
    
    return:
        list[dict]: List of users with id, username and email
    """
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
                       SELECT user_id, username, email 
                       FROM users
                       WHERE user_type = 'User'
                       ORDER BY username
                       """)
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching users: {e}")
        return[]
    finally:
        cursor.close()
        conn.close()
        
def get_user_ba_positions(user_id):
    """
    Gets all job positions assigned to BAs that the user is a member of.
    
    param:
        user_id(int): ID of the user.
    
    return:
        list[dict]: List of positions with BA information.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT jp.position_id,
            jp.position_title,
            jp.department,
            jp.kenziffer,
            jp.status,
            ba.ba_name,
            bm.is_head as is_ba_head
            FROM ba_members bm
            JOIN berufungsausschuss ba ON bm.ba_id = ba.ba_id
            JOIN job_positions jp ON ba.ba_id = jp.ba_id
            WHERE bm.user_id = %s
            AND jp.status IN ('created', 'in_progress')
            ORDERED BY jp.created_at DESC
            """, (user_id,))
        return cursor.fetchall()
    except Exception as e:
        print(f"Error getting user BA : {e}")
        return []
    finally:
        cursor.close()
        conn.close()     

        
def get_user_assigned_positions(user_id):
    """Get positions assigned to a specific BA user"""
    conn =get_db_connection()
    cursor= conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
                       SELECT jp.* FROM job_positions jp
                       JOIN ba_members bm ON jp.ba_id = bm.ba_id
                       WHERE bm.user_id = %s AND jp.status IN ('created', 'in_progress')
                       """, (user_id,))
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching user positions:{e}")
        return[]
    finally:
        cursor.close()
        conn.close()
        
# =============================================================================
# CREATION FUNCTION
# =============================================================================

def get_all_procedures():
    """
    Get all available procedure for job positions
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
                       SELECT procedure_id, procedure_title, grundlage
                       FROM procedures
                       ORDER BY procedure_title
                       """)
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching procedur: {e}")
        return[]
    finally:
        cursor.close()
        conn.close()
        
def create_ba_committee_with_position(position_title, department, kenziffer,procedure_id, created_by, ba_name, member_ids, head_id):
    """
    Creates a job position
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Start transaction
        conn.start_transaction()
        
        # 1. Create BA committee first 
        cursor.execute("""
                        INSERT INTO berufungsausschuss (ba_name, created_by)
                        VALUES (%s, %s)""", (ba_name, created_by))
        ba_id = cursor.lastrowid
        
        #2. Add BA members
        for member_id in member_ids:
            is_head = (member_id == head_id)
            cursor.execute("""
                           INSERT INTO ba_members(ba_id, user_id,is_head)
                           VALUES(%s, %s, %s)
                           """, (ba_id, member_id, is_head))
            
        # 3. Create job position
        cursor.execute("""
                       INSERT INTO job_positions(position_title, department, kenziffer, procedure_id, created_by, ba_id, status)
                       VALUES(%s, %s, %s, %s, %s, %s,'created')
                       """,(position_title, department, kenziffer, procedure_id, created_by, ba_id))
        position_id = cursor.lastrowid
        
        # Commit transaction
        conn.commit()
        
        return{
            'success': True,
            'position_id': position_id,
            'ba_id': ba_id
        }
    except Exception as e:
        conn.rollback()
        if "kenziffer" in str(e):
            return{'success': False, 'error': 'Refremce number(kenziffer) already exists'}
        else:
            return{'success': False, 'error': str(e) }
    finally:
        cursor.close()
        conn.close()
        