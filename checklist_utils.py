from typing import Dict, Any, cast
from db_utils import get_db_connection

def get_full_procedure_data(position_id: int, user_id: int):
    """
    Fetches the complete procedure structure dynamically for a given job position.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    
    # this query starts from the job_position and joins to find its specific procedure.
    query = """
        SELECT 
            p.procedure_title,
            ph.phase_id,
            ph.phase_title,
            ph.phase_order,
            ph.link_url AS phase_link,
            ps.step_id,
            ps.step_title,
            ps.step_order,
            ps.responsible_user_type,
            ps.link_url AS step_link,
            st.task_id,
            st.task_description,
            st.task_order,
            st.required_documents,
            st.link_url AS task_link,
            up.status AS task_status
        FROM job_positions jp
        JOIN procedures p ON jp.procedure_id = p.procedure_id
        JOIN procedure_phases ph ON p.procedure_id = ph.procedure_id
        JOIN procedure_steps ps ON ph.phase_id = ps.phase_id
        JOIN step_tasks st ON ps.step_id = st.step_id
        LEFT JOIN user_progress up ON st.task_id = up.task_id AND up.position_id = jp.position_id AND up.user_id = %s
        WHERE jp.position_id = %s
        ORDER BY ph.phase_order, ps.step_order, st.task_order;
    """
    
    try:
        # The order of parameters must match the query: user_id first, then position_id.
        cursor.execute(query, (user_id, position_id))
        results = cursor.fetchall()
        
        phases: Dict[int, Dict[str, Any]] = {}
        for row in results:
            row_dict = cast(Dict[str, Any], row)
            phase_id = row_dict['phase_id']
            if phase_id not in phases:
                # Removed "phase_code"
                phases[phase_id] = {
                    "phase_title": row_dict['phase_title'],
                    "phase_link": row_dict['phase_link'],
                    "steps": {}
                }
            
            step_id = row_dict['step_id']
            if step_id not in phases[phase_id]['steps']:
                # Removed "step_code"
                 phases[phase_id]['steps'][step_id] = {
                    "step_title": row_dict['step_title'],
                    "responsible": row_dict['responsible_user_type'],
                    "step_link": row_dict['step_link'],
                    "tasks": []
                 }
            
            if row_dict['task_status'] is None:
                row_dict['task_status'] = 'not_started'

            phases[phase_id]['steps'][step_id]['tasks'].append(row_dict)
            
        return phases

    except Exception as e:
        print(f"Error fetching checklist data: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def flatten_procedure_to_steps(phases_data):
    """
    Converts the nested phases dictionary into a flat list of steps.
    """
    flat_steps = []
    sorted_phase_ids = sorted(phases_data.keys())
    
    for phase_id in sorted_phase_ids:
        phase = phases_data[phase_id]
        sorted_step_ids = sorted(phase['steps'].keys())
        
        for step_id in sorted_step_ids:
            step = phase['steps'][step_id]
            step['parent_phase_title'] = phase['phase_title']
            flat_steps.append(step)
            
    return flat_steps


def update_task_status(user_id: int, position_id: int, task_id: int, new_status: str):
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
        

def get_all_positions():
    """
    Fetches all active job positions for the dropdown selection.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT position_id, position_title, kenziffer, department 
            FROM job_positions 
            WHERE status IN ('created', 'in_progress')
            ORDER BY position_id DESC
        """)
        positions = cursor.fetchall()
        return positions
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []
    finally:
        cursor.close()
        conn.close()