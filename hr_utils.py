from db_utils import get_db_cursor

# =============================================================================
# JOB POSITION FUNCTIONS
# =============================================================================
def get_active_positions():
    """
    Gets all active positions with BA assignments and progress for Hr dashboard 
    
    return:
        list[dict]: All positions with their BA and progress info.
        """
        
    with get_db_cursor() as (conn, cursor):
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
    



def get_position_statistics():
    """
    Gets overall statistics for all postions for HR dashboard
    
    return:
        dict: Statistics including counts and averages
        """
    try: 
        with get_db_cursor() as (conn, cursor):   
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
    
    
# =============================================================================
# BA COMITTEE FUNCTIONS
# =============================================================================

def get_all_ba_groups():
    """
    Gets all BA groups for HR dashboard.
    
    return:
        list[dict]: List of all BA groups with member counts.
    """
    with get_db_cursor() as (conn, cursor):
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
    

def get_ba_members(ba_id):
    """Get all members of a specific BA group"""
    with get_db_cursor() as (conn, cursor):
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
        
   
        
# =============================================================================
# USER AND POSITION ASSIGNMENT FUNCTIONS
# =============================================================================

def get_available_users_for_ba():
    """
    Gets all USER type users who can be assigned to a BA
    
    return:
        list[dict]: List of users with id, username and email
    """
    
    with get_db_cursor() as (conn, cursor):
        cursor.execute("""
                       SELECT user_id, username, email 
                       FROM users
                       WHERE user_type = 'User'
                       ORDER BY username
                       """)
        return cursor.fetchall()
    
    
        
# =============================================================================
# CREATION FUNCTION
# =============================================================================

def get_all_procedures():
    """
    Get all available procedure for job positions
    """
    with get_db_cursor() as (conn, cursor):
        cursor.execute("""
                       SELECT procedure_id, procedure_title, grundlage
                       FROM procedures
                       ORDER BY procedure_title
                       """)
        return cursor.fetchall()
    
        
def create_ba_committee_with_position(position_title, department, kenziffer,procedure_id, created_by, ba_name, member_ids, head_id):
    """
    Creates a job position
    """
    try:
        with get_db_cursor() as (conn, cursor):
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
        if "kenziffer" in str(e):
            return {'success': False, 'error': 'Reference number (kenziffer) already exists'}
        else:
            return {'success': False, 'error': str(e)}