import os
import re
import json
from flask import Flask, render_template_string, jsonify
import subprocess

app = Flask(__name__)

# Server configuration
SERVERS = {
    "Server 1": "72.61.254.71",
    "Server 2": "72.61.254.74"
}
SSHPASS = "Gunduata@123"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>WebSocket Log Dashboard</title>
    <style>
        body { font-family: sans-serif; background: #1e1e1e; color: #d4d4d4; margin: 20px; }
        .server-section { margin-bottom: 30px; border: 1px solid #333; padding: 15px; border-radius: 8px; }
        h2 { color: #569cd6; margin-top: 0; }
        .log-container { 
            background: #000; 
            padding: 10px; 
            height: 300px; 
            overflow-y: scroll; 
            font-family: monospace; 
            font-size: 12px;
            border: 1px solid #444;
        }
        .error { color: #f44747; font-weight: bold; }
        .info { color: #b5cea8; }
        .warning { color: #dcdcaa; }
        .timestamp { color: #808080; }
        .controls { margin-bottom: 10px; }
        button { background: #333; color: white; border: 1px solid #555; padding: 5px 10px; cursor: pointer; }
        button:hover { background: #444; }
    </style>
    <script>
        async function fetchLogs(server) {
            const response = await fetch(`/logs/${server}`);
            const data = await response.json();
            const container = document.getElementById(`logs-${server}`);
            
            if (data.error) {
                container.innerHTML = `<div class="error">Error fetching logs: ${data.error}</div>`;
                return;
            }

            const lines = data.logs.split('\\n');
            const formatted = lines.map(line => {
                if (line.includes('ERROR')) return `<div class="error">${line}</div>`;
                if (line.includes('WARNING')) return `<div class="warning">${line}</div>`;
                return `<div class="info">${line}</div>`;
            }).join('');
            
            container.innerHTML = formatted;
            container.scrollTop = container.scrollHeight;
        }

        function refreshAll() {
            fetchLogs('Server 1');
            fetchLogs('Server 2');
        }

        setInterval(refreshAll, 5000);
        window.onload = refreshAll;
    </script>
</head>
<body>
    <h1>WebSocket Log Dashboard</h1>
    <div class="controls">
        <button onclick="refreshAll()">Refresh Now</button>
    </div>

    <div class="server-section">
        <h2>Server 1 (72.61.254.71) - Web Logs</h2>
        <div id="logs-Server 1" class="log-container">Loading...</div>
    </div>

    <div class="server-section">
        <h2>Server 2 (72.61.254.74) - Web Logs</h2>
        <div id="logs-Server 2" class="log-container">Loading...</div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/logs/<server_name>')
def get_logs(server_name):
    ip = SERVERS.get(server_name)
    if not ip:
        return jsonify({"error": "Invalid server name"})

    try:
        cmd = f"export SSHPASS='{SSHPASS}' && sshpass -e ssh -o StrictHostKeyChecking=no root@{ip} 'cd /root/apk_of_ata && docker compose logs --tail=50 web'"
        result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
        return jsonify({"logs": result})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e.output)})
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005)
