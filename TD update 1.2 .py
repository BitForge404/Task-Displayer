# Update 1.2

# Added live Time and Date display at the top of the Display window
# Added heading above task list in the Display window
# Replaced delete button with a "Complete & Archive" button that requires a confirmation number input to move tasks to history
# The code for the delete button is still kept for backward compatibility (line 658) but not exposed in the UI.
# All archived tasks are preserved in history and not deleted, they can be viewed in the completed history dialog on the web UI and PyQt display
# Tasks can only be archived when a confirmation number is provided
# Tasks receive timestamps when created and when completed for better tracking, these timestamps, along with the confirmation number are shown in both the web UI and PyQt display
# Made the completed task history window look nice with the necessary details and color coding
# Updated the web page to look a lot better and to be mobile and desktop friendly

import threading
import queue
from flask import Flask, request, render_template_string
from TD_completed_list_template import COMPLETED_LIST
from PyQt5 import QtWidgets, QtCore, QtGui
import sys, sqlite3, subprocess, time, threading, socket, datetime
import logging
import html  # for escaping HTML in task names
# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Shared queues for tasks and display updates (thread-safe)
task_queue = queue.Queue()
display_update_queue = queue.Queue()

# SQLite setup for persistence
conn = sqlite3.connect('tasks.db', check_same_thread=False)

# Lock for database operations
db_lock = threading.Lock()

# Create initial table structure if it doesn't exist
conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
    name TEXT, 
    priority TEXT, 
    displayed INTEGER DEFAULT 0,
    timestamp TEXT,
    completed INTEGER DEFAULT 0,
    completed_at TEXT
)''')

# If upgrading from older version, ensure all columns exist
cursor = conn.execute("PRAGMA table_info(tasks)")
cols = [row[1] for row in cursor]

# Add any missing columns
if 'timestamp' not in cols:
    conn.execute('ALTER TABLE tasks ADD COLUMN timestamp TEXT')
if 'completed' not in cols:
    conn.execute('ALTER TABLE tasks ADD COLUMN completed INTEGER DEFAULT 0')
if 'completed_at' not in cols:
    conn.execute('ALTER TABLE tasks ADD COLUMN completed_at TEXT')
if 'confirm_number' not in cols:
    conn.execute('ALTER TABLE tasks ADD COLUMN confirm_number INTEGER')
conn.commit()

# Define priority order for sorting
PRIORITY_ORDER = {'High': 3, 'Medium': 2, 'Low': 1}

# Color mapping for priorities (used in the display)
PRIORITY_COLORS = {'High': '#d32f2f', 'Medium': '#ff9800', 'Low': '#388e3c'}

# Timestamp font size (change this number to adjust timestamp size in both GUI and web UI)
TIMESTAMP_FONT_SIZE = 32  # px

# Separate font size for completed tasks history window
COMPLETED_TASKS_FONT_SIZE = 16  # px

# Flask app for remote input and task management
app = Flask(__name__)

# HTML form for task submission
INPUT_FORM = '''
<!doctype html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Add Task</title>
    <style>
        :root{ --bg:#f7f8fb; --card:#ffffff; --accent:#1976d2; --muted:#6b6f76 }
        *{box-sizing:border-box}
        body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;background:var(--bg);padding:16px}
        .wrap{max-width:720px;margin:0 auto}
        .card{background:var(--card);border-radius:12px;padding:18px;box-shadow:0 6px 18px rgba(20,20,30,0.06)}
        h1{margin:0 0 12px;font-size:20px;color:#222;text-align:center}
        form{display:flex;flex-direction:column;gap:12px}
        label{font-size:13px;color:var(--muted)}
        input[type=text],select,input[type=number]{width:100%;padding:12px;border-radius:8px;border:1px solid #e6e9ef;font-size:15px}
        input[type=text]:focus,select:focus,input[type=number]:focus{outline:none;border-color:var(--accent)}
        .row{display:flex;gap:8px}
        .btn{width:100%;padding:12px;border-radius:8px;border:none;background:var(--accent);color:#fff;font-weight:600;cursor:pointer}
        .secondary{background:var(--accent);color:#fff}
        .message{margin-top:12px;padding:10px;border-radius:8px;text-align:center}
        @media(min-width:520px){.row{flex-direction:row}.two{flex:1}}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="card">
            <h1>Add a New Task</h1>
            <form method="post" action="/">
                <div>
                    <label for="task_name">Task</label>
                    <input id="task_name" type="text" name="task_name" placeholder="Describe the task" required maxlength="1000">
                </div>
                <div class="row">
                    <div class="two">
                        <label for="priority">Priority</label>
                        <select id="priority" name="priority" required>
                            <option value="" disabled selected>Choose priority</option>
                            <option value="High">High</option>
                            <option value="Medium">Medium</option>
                            <option value="Low">Low</option>
                        </select>
                    </div>
                </div>
                <button class="btn" type="submit">Add Task</button>
            </form>
            <a href="/tasks" style="display:block;margin-top:10px;text-decoration:none"><button class="btn secondary">View Tasks</button></a>
            {% if message %}
                <div class="message {% if 'successfully' in message %}success{% else %}error{% endif %}">{{ message }}</div>
            {% endif %}
        </div>
    </div>
</body>
</html>
'''

# HTML for task list with delete buttons
TASK_LIST = '''
<!doctype html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Tasks</title>
    <style>
        :root{--bg:#f7f8fb;--card:#fff;--accent:#1976d2;--muted:#6b6f76}
        *{box-sizing:border-box}
    body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;background:var(--bg);padding:14px;overflow-x:hidden;-webkit-overflow-scrolling:touch}
    .wrap{max-width:780px;width:100%;margin:0 auto;padding:0 8px}
    header{display:flex;align-items:center;gap:12px;margin-bottom:14px}
    h1{margin:0;font-size:18px;color:#222}
    .card{background:var(--card);padding:12px;border-radius:10px;box-shadow:0 6px 18px rgba(20,20,30,0.04);overflow:hidden}
        ul{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:12px}
        li{display:flex;flex-direction:column;gap:8px;padding:12px;border-radius:10px;border:1px solid #eef2f7;background:var(--card)}
        .meta{display:flex;flex-direction:column;width:100%}
        .ts{color:var(--muted);font-size:12px;margin-bottom:2px}
        .title{display:flex;gap:8px;align-items:flex-start;width:100%}
        .priority{font-weight:700;color:#222;white-space:nowrap}
    .name{color:#222;overflow-wrap:anywhere;word-break:break-word;white-space:normal;line-height:1.4;flex:1}
        form{display:flex;gap:8px;align-items:center;width:100%;padding-top:4px}
        input[type=number],input[type=text]{padding:8px;border-radius:8px;border:1px solid #e2e6ef;width:80px}
        .btn{padding:8px 12px;border-radius:8px;border:none;background:var(--accent);color:#fff;cursor:pointer}
        .link-btn{background:var(--accent);color:#fff}
        @media(max-width:480px){.ts{font-size:12px}.btn{padding:8px 10px}}
    </style>
</head>
<body>
    <div class="wrap">
            <header>
                <a href="/" style="text-decoration:none;margin-right:8px"><button class="btn link-btn">Back</button></a>
                <h1 style="margin:0">Tasks</h1>
                <div style="margin-left:auto"><a href="/history" style="text-decoration:none"><button class="btn link-btn">View Completed</button></a></div>
            </header>
        <div class="card">
            {% if tasks %}
                <ul>
                    {% for task in tasks %}
                        <li>
                            <div class="meta">
                                                <div class="ts"><span style="font-size:11px">{{ task.timestamp_short }}</span></div>
                                <div class="title"><div class="priority">{{ task.priority }}:</div><div class="name">{{ task.name }}</div></div>
                            </div>
                            <form method="post" action="/move_task">
                                <input type="hidden" name="name" value="{{ task.name }}">
                                <input type="hidden" name="priority" value="{{ task.priority }}">
                                <input type="hidden" name="timestamp" value="{{ task.timestamp }}">
                                <input type="text" name="confirm_number" required placeholder="#" style="width:84px" min="0">
                                <button class="btn" type="submit">Complete</button>
                            </form>
                        </li>
                    {% endfor %}
                </ul>
            {% else %}
                <p style="margin:12px 0;color:var(--muted)">No tasks available.</p>
            {% endif %}
            <!-- Back button moved to header -->
        </div>
    </div>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def handle_input():
    message = ''
    if request.method == 'POST':
        task_name = request.form.get('task_name')
        priority = request.form.get('priority')
        if task_name and priority in PRIORITY_ORDER:
            if len(task_name) <= 1000:  # Basic input validation
                # timestamp for the task (ISO format stored)
                ts = datetime.datetime.now().isoformat()
                with db_lock:
                    task_queue.put({'name': task_name, 'priority': priority, 'timestamp': ts})
                    conn.execute('INSERT INTO tasks (name, priority, displayed, timestamp) VALUES (?, ?, 0, ?)', (task_name, priority, ts))
                    conn.commit()
                message = 'Task submitted successfully!'
                # Signal display update via queue instead of direct call
                display_update_queue.put(True)
            else:
                message = 'Task name too long (max 1000 characters).'
        else:
            message = 'Please provide a valid task name and priority.'
    return render_template_string(INPUT_FORM, message=message)

@app.route('/tasks')
def show_tasks():
    try:
        # Only show active (not moved/completed) tasks on the main task list
        cursor = conn.execute('''
            SELECT name, priority, timestamp 
            FROM tasks 
            WHERE completed = 0 OR completed IS NULL
            ORDER BY priority DESC, name
        ''')
        tasks = []
        for row in cursor:
            name, priority, ts = row[0], row[1], row[2]
            # Format short timestamp for display (dd/mm/yy hh:MM AM/PM) and wrap in brackets
            ts_short = ''
            if ts:
                try:
                    dt = datetime.datetime.fromisoformat(ts)
                    ts_short = f"[{dt.strftime('%d/%m/%y %I:%M %p')}]"
                except Exception:
                    ts_short = f"[{ts}]"
            tasks.append({'name': name, 'priority': priority, 'timestamp': ts, 'timestamp_short': ts_short})
    except Exception as e:
        logger.error(f"Failed to fetch tasks: {e}")
        return '<script>alert("Failed to load tasks"); window.location="/"</script>'
    tasks.sort(key=lambda x: (-PRIORITY_ORDER[x['priority']], x['name']))
    # Inject the timestamp font size into the template CSS (simple replace placeholder)
    template = TASK_LIST.replace('font-size:12px', f'font-size:{TIMESTAMP_FONT_SIZE}px')
    return render_template_string(template, tasks=tasks)

@app.route('/delete_task', methods=['POST'])
def delete_task():
    # Keep for backward compatibility but do not expose it in the UI.
    name = request.form.get('name')
    priority = request.form.get('priority')
    timestamp = request.form.get('timestamp')
    if name and priority:
        if timestamp:
            conn.execute('DELETE FROM tasks WHERE name = ? AND priority = ? AND timestamp = ?', (name, priority, timestamp))
        else:
            conn.execute('DELETE FROM tasks WHERE name = ? AND priority = ?', (name, priority))
        conn.commit()
    return '<script>window.location="/tasks"</script>'


@app.route('/move_task', methods=['POST'])
def move_task():
    # Archive/complete a task by moving it to history
    name = request.form.get('name')
    priority = request.form.get('priority')
    timestamp = request.form.get('timestamp')
    confirm_number = request.form.get('confirm_number')
    
    # Validate required fields
    if not all([name, priority, confirm_number]):
        return '<script>alert("Please fill in all required fields including the confirmation number"); window.location="/tasks"</script>'
    
    # In case the confirmation number is only supposed to be numeric, uncomment below and change line 142 input type to number
    
    #try:
        # Convert confirmation number to int (validates it's a proper number)
    #    confirm_number = int(confirm_number)
    #except ValueError:
    #    return '<script>alert("Please enter a valid number"); window.location="/tasks"</script>'
    
    completed_ts = datetime.datetime.now().isoformat()
    
    try:
        # First verify the task exists and isn't already completed
        if timestamp:
            cursor = conn.execute('''SELECT 1 FROM tasks 
                                   WHERE name = ? AND priority = ? AND timestamp = ? AND completed = 0''',
                                (name, priority, timestamp))
        else:
            cursor = conn.execute('''SELECT 1 FROM tasks 
                                   WHERE name = ? AND priority = ? AND completed = 0''',
                                (name, priority))
        
        if not cursor.fetchone():
            return '<script>alert("Task not found or already completed"); window.location="/tasks"</script>'
        
        # Move the task to history
        if timestamp:
            conn.execute('''UPDATE tasks 
                          SET completed = 1, completed_at = ?, confirm_number = ? 
                          WHERE name = ? AND priority = ? AND timestamp = ? AND completed = 0''', 
                       (completed_ts, confirm_number, name, priority, timestamp))
        else:
            conn.execute('''UPDATE tasks 
                          SET completed = 1, completed_at = ?, confirm_number = ? 
                          WHERE name = ? AND priority = ? AND completed = 0''', 
                       (completed_ts, confirm_number, name, priority))
        
        affected = conn.total_changes
        conn.commit()
        
        if affected == 0:
            return '<script>alert("No task was updated. It may have been already completed."); window.location="/tasks"</script>'
            
    except Exception as e:
        logger.error(f"Failed to move task to history: {e}")
        conn.rollback()
        return '<script>alert("Failed to move task to history"); window.location="/tasks"</script>'
            
    return '<script>window.location="/tasks"</script>'


@app.route('/history')
def history():
    cursor = conn.execute('SELECT name, priority, timestamp, completed_at, confirm_number FROM tasks WHERE completed = 1 ORDER BY completed_at DESC')
    tasks = []
    for row in cursor:
        name, priority, ts, completed_at, confirm_number = row[0], row[1], row[2], row[3], row[4]
        ts_short = ''
        completed_short = ''
        if ts:
            try:
                dt = datetime.datetime.fromisoformat(ts)
                ts_short = f"[{dt.strftime('%d/%m/%y %H:%M')}]"
            except Exception:
                ts_short = f"[{ts}]"
        if completed_at:
            try:
                dt2 = datetime.datetime.fromisoformat(completed_at)
                completed_short = f"[{dt2.strftime('%d/%m/%y %H:%M')}]"
            except Exception:
                completed_short = f"[{completed_at}]"
        tasks.append({'name': name, 'priority': priority, 'timestamp_short': ts_short, 'completed_short': completed_short, 'confirm_number': confirm_number})
    template = COMPLETED_LIST.replace('font-size:12px', f'font-size:{TIMESTAMP_FONT_SIZE}px')
    return render_template_string(template, tasks=tasks)

# PyQt display window
class DisplayWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Task Display")
        self.resize(600, 400)

        # Layout
        self.layout = QtWidgets.QVBoxLayout(self)
        
        # DateTime display at the top
        self.datetime_label = QtWidgets.QLabel(self)
        self.datetime_label.setAlignment(QtCore.Qt.AlignCenter)
        font = QtGui.QFont("Arial", 18)
        self.datetime_label.setFont(font)
        self.datetime_label.setStyleSheet("""
            QLabel {
                color: #333;
                padding: 10px;
                background: #f8f9fa;
                border-radius: 5px;
            }
        """)
        self.layout.addWidget(self.datetime_label)
        
        # Separator line
        separator = QtWidgets.QFrame(self)
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        separator.setStyleSheet("QFrame { background: #ccc; margin: 10px 0; }")
        separator.setFixedHeight(2)
        self.layout.addWidget(separator)

        # Heading for tasks with a Completed History button
        heading_container = QtWidgets.QWidget(self)
        heading_layout = QtWidgets.QHBoxLayout(heading_container)
        heading_label = QtWidgets.QLabel("To do:", self)
        heading_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        heading_font = QtGui.QFont("Arial", 23, QtGui.QFont.Bold)
        heading_label.setFont(heading_font)
        heading_layout.addWidget(heading_label)
        # Spacer
        heading_layout.addStretch()
        history_btn = QtWidgets.QPushButton("Completed History", self)
        history_btn.setFixedHeight(45)
        history_btn.setMinimumWidth(180)
        history_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2d6da3;
            }
        """)
        history_btn.clicked.connect(self.show_history_dialog)
        heading_layout.addWidget(history_btn)
        self.layout.addWidget(heading_container)
        
        # Task display widget
        self.text_area = QtWidgets.QTextEdit(self)
        self.text_area.setReadOnly(True)
        # Allow HTML so we can color labels and add spacing
        try:
            self.text_area.setAcceptRichText(True)
        except Exception:
            # setAcceptRichText may not be available in some Qt bindings; ignore if so
            pass
        font = QtGui.QFont("Arial", 23)
        self.text_area.setFont(font)
        self.text_area.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 10px;
                color: #333;
            }
        """)
        self.layout.addWidget(self.text_area)

        # Timer to update display
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)

    def update_display(self):
        # Update datetime display
        current_dt = QtCore.QDateTime.currentDateTime()
        formatted_dt = current_dt.toString('dddd, MMMM d, yyyy - hh:mm:ss AP')
        self.datetime_label.setText(formatted_dt)
        
        # Check for update signals
        while not display_update_queue.empty():
            display_update_queue.get()
            
        # Fetch new tasks from queue
        while not task_queue.empty():
            task = task_queue.get()

        # Get new tasks from SQLite (include timestamp) — only non-completed ones
        with db_lock:
            cursor = conn.execute('SELECT name, priority, timestamp FROM tasks WHERE displayed = 0 AND completed = 0')
        new_tasks = [{'name': row[0], 'priority': row[1], 'timestamp': row[2]} for row in cursor]

        # Mark tasks as displayed (use timestamp to target specific rows)
        for task in new_tasks:
            if task.get('timestamp'):
                conn.execute('UPDATE tasks SET displayed = 1 WHERE name = ? AND priority = ? AND timestamp = ?', (task['name'], task['priority'], task['timestamp']))
            else:
                conn.execute('UPDATE tasks SET displayed = 1 WHERE name = ? AND priority = ?', (task['name'], task['priority']))
        conn.commit()

        # Get all active (non-completed) tasks for sorting (include timestamp)
        cursor = conn.execute('SELECT name, priority, timestamp FROM tasks WHERE completed = 0')
        all_tasks = []
        for row in cursor:
            name, priority, ts = row[0], row[1], row[2]
            ts_short = ''
            if ts:
                try:
                    dt = datetime.datetime.fromisoformat(ts)
                    ts_short = f"[{dt.strftime('%d/%m/%y %I:%M %p')}]"
                except Exception:
                    ts_short = f"[{ts}]"
            all_tasks.append({'name': name, 'priority': priority, 'timestamp': ts, 'timestamp_short': ts_short})

        # Sort tasks by priority (High > Medium > Low) and then by name
        all_tasks.sort(key=lambda x: (-PRIORITY_ORDER[x['priority']], x['name']))

        # Update display with colored priorities and increased spacing
        self.text_area.clear()
        for task in all_tasks:
            color = PRIORITY_COLORS.get(task['priority'], '#000')
            name_escaped = html.escape(task['name'])
            ts_display = html.escape(task.get('timestamp_short', ''))
            item_html = (f"<div style='margin-bottom:20px; line-height:1.5;'>"
                         f"<div style='color:#666; font-size:{TIMESTAMP_FONT_SIZE}px; margin-bottom:30px;'>{ts_display}</div>"
                         f"<span style='color:{color}; font-weight:700; margin-right:15px;'>{task['priority']}:</span>"
                         f"<span style='color:#222;'>{name_escaped}</span>"
                         f"</div>")
            self.text_area.append(item_html)

    def clear_tasks(self):
        self.text_area.clear()
        # Only clear active tasks; preserve completed/history
        conn.execute('DELETE FROM tasks WHERE completed = 0')
        conn.commit()

    def show_history_dialog(self):
        # Open a dialog that lists completed tasks
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle('Completed Tasks')
        dialog.resize(2000, 1200)
        dlg_layout = QtWidgets.QVBoxLayout(dialog)
        text = QtWidgets.QTextEdit(dialog)
        
        # Configure text widget
        text.setReadOnly(True)
        text.setAcceptRichText(True)
        font = QtGui.QFont("Arial", COMPLETED_TASKS_FONT_SIZE)
        text.setFont(font)

        # Fetch completed tasks with explicit column names
        cursor = conn.execute('''
            SELECT 
                name,
                priority,
                timestamp,
                completed_at,
                confirm_number
            FROM tasks 
            WHERE completed = 1 
            ORDER BY completed_at DESC
        ''')
        
        # Debug print column names
        print("Debug - Column names:", [description[0] for description in cursor.description])
        
        lines = []
        for row in cursor:
            try:
                name = str(row[0] if row[0] is not None else '')
                priority = str(row[1] if row[1] is not None else '')
                ts = row[2]
                completed_at = row[3]
                confirm_number = row[4]
                
                # Debug print for each row
                print(f"Debug - Row data: name='{name}', priority='{priority}', confirm_number={confirm_number}")
                
                created = ''
                completed = ''
            except Exception as e:
                print(f"Error processing row: {e}")
                continue
            if ts:
                try:
                    dt = datetime.datetime.fromisoformat(ts)
                    created = f"[{dt.strftime('%d/%m/%y %I:%M %p')}]"
                except Exception:
                    created = f"[{ts}]"
            if completed_at:
                try:
                    dt2 = datetime.datetime.fromisoformat(completed_at)
                    completed = f"[{dt2.strftime('%d/%m/%y %I:%M %p')}]"
                except Exception:
                    completed = f"[{completed_at}]"
                
            # Debug print to check the values
            print(f"Debug - name: {name}, priority: {priority}, confirm_number: {confirm_number}")
            
            # Format each task with HTML for colors and spacing
            task_html = (
                f'<div style="margin-bottom: 20px; line-height: 1.8;">'
                f'<span style="color: #2196F3; white-space: nowrap;">{created}</span>&nbsp;&nbsp;'  # Blue for creation time
                f'<span style="color: #4CAF50; white-space: nowrap;">{completed}</span>'  # Green for completion time
                f'{"&nbsp;&nbsp;" if confirm_number else ""}'
                f'<span style="color: #ff1744; font-weight: bold; white-space: nowrap;">#{confirm_number}</span>&nbsp;&nbsp;'  # Red confirmation number
                f'<span style="font-weight: bold; color: #333;">{priority}:</span>&nbsp;'  # Priority label
                f'<span style="color: #222;">{html.escape(str(name))}</span>'  # Task name
                f'</div>'
            )
            lines.append(task_html)

        # Set content
        text.setHtml(''.join(lines) if lines else '<p>No completed tasks yet.</p>')
        dlg_layout.addWidget(text)
        
        # Close button with styling
        close_btn = QtWidgets.QPushButton('Close', dialog)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px 16px;
                color: #333;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
        """)
        close_btn.clicked.connect(dialog.accept)
        dlg_layout.addWidget(close_btn)
        
        # Set dialog styling
        dialog.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
        """)
        
        dialog.exec_()

# Run Flask in a thread
def run_flask():
    try:
        logger.info("Starting Flask on http://0.0.0.0:5000")
        app.run(host='0.0.0.0', port=5000, use_reloader=False, threaded=True)
    except Exception as e:
        logger.error(f"Flask failed to start: {e}")
        import traceback
        traceback.print_exc()

# Main function to start PyQt and Flask
def main():
    # Start Flask server thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True  # Run Flask in background
    flask_thread.start()

    # Start cloudflared in a background daemon thread so it doesn't block the main thread
    cloudflared_thread = threading.Thread(target=run_cloudflared, daemon=True)
    cloudflared_thread.start()

    # Start PyQt application in fullscreen
    app = QtWidgets.QApplication(sys.argv)
    display_window = DisplayWindow()
    display_window.showFullScreen()
    sys.exit(app.exec_())
    
    # Start Cloudflare Tunnel
def run_cloudflared():
    # Wait until Flask is actually listening
    print("Waiting for Flask to start on port 5000...")
    while True:
        try:
            with socket.create_connection(("localhost", 5000), timeout=1):
                print("Flask is ready!")
                break
        except:
            time.sleep(0.5)

    # Now start tunnel
    cloudflared_path = r'C:\Users\lucas\OneDrive\Desktop\codes\Python\Cloudflare\cloudflared-windows-amd64.exe'
    print("Starting public tunnel...")
    # Start cloudflared as a separate process so it doesn't block this thread indefinitely.
    try:
        subprocess.Popen([cloudflared_path, 'tunnel', '--url', 'http://localhost:5000'], stdout=None, stderr=None)
    except Exception as e:
        logger.error(f"Failed to start cloudflared: {e}")
    

if __name__ == '__main__':
    main() # Start the main function