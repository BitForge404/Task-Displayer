COMPLETED_LIST = '''
<!doctype html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Completed Tasks</title>
    <style>
        :root{--bg:#f7f8fb;--card:#fff;--accent:#1976d2;--muted:#6b6f76}
        *{box-sizing:border-box}
        body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;background:var(--bg);padding:14px}
        .wrap{max-width:780px;margin:0 auto}
        header{display:flex;align-items:center;gap:12px;margin-bottom:14px}
        h1{margin:0;font-size:18px;color:#222}
        .card{background:var(--card);padding:12px;border-radius:10px;box-shadow:0 6px 18px rgba(20,20,30,0.04)}
        ul{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:10px}
        li{padding:12px;border-radius:8px;border:1px solid #eef2f7;display:flex;flex-direction:column}
        .times{color:var(--muted);font-size:10px;margin-bottom:4px}
        .row{display:flex;gap:8px;align-items:flex-start;flex:1}
        .prio{font-weight:700;color:#333;white-space:nowrap}
        .name{color:#222;word-wrap:break-word;line-height:1.4;flex:1}
        .btn{padding:8px 12px;border-radius:8px;border:none;background:var(--accent);color:#fff;cursor:pointer}
        .link-btn{background:var(--accent);color:#fff}
    </style>
</head>
<body>
    <div class="wrap">
        <header>
            <a href="/tasks" style="text-decoration:none"><button class="btn link-btn">Back</button></a>
            <h1>Completed Tasks</h1>
        </header>
        <div class="card">
            {% if tasks %}
                <ul>
                    {% for task in tasks %}
                        <li>
                            <div class="times">Created: <span style="font-size:10px">{{ task.timestamp_short }}</span> &nbsp; Completed: <span style="font-size:10px">{{ task.completed_short }}</span></div>
                            <div class="row"><div class="prio">{{ task.priority }}:</div><div class="name">{{ task.name }}</div></div>
                        </li>
                    {% endfor %}
                </ul>
            {% else %}
                <p style="color:var(--muted)">No completed tasks yet.</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
'''
