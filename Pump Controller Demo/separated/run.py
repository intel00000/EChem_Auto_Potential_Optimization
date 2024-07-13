import subprocess
import time
import os

# Start the backend server
backend_process = subprocess.Popen(["python", os.path.join("backend", "backend.py")])

# Wait for the backend to start
time.sleep(2)

# Start the frontend application
frontend_process = subprocess.Popen(["python", os.path.join("frontend", "frontend.py")])

# Wait for the frontend to finish
frontend_process.wait()

# Terminate the backend server when the frontend exits
backend_process.terminate()