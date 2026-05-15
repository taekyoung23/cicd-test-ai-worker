import os

required = [
    "worker.py",
    "inference.py",
    "config.py",
    "model_scripts",
]

for path in required:
    if not os.path.exists(path):
        raise FileNotFoundError(path)

print("healthcheck ok")
