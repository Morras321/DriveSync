"""
DriveSync - Application Entry Point
Creates the Flask app, registers the Blueprint, and starts the server.
"""

import argparse
import platform
import socket

from flask import Flask
from flask_cors import CORS

from config import BASE_DIR, MUSIC_DIR, PLAYLIST_DIR
from routes import api

app = Flask(__name__, static_folder=str(BASE_DIR / "frontend"), static_url_path="")
CORS(app)
app.register_blueprint(api)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DriveSync Server")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000,
                        help="Port to bind to (default: 5000)")
    parser.add_argument("--debug", action="store_true",
                        help="Enable Flask debug mode")
    args = parser.parse_args()

    print("🎵 DriveSync Server starting...")
    print(f"📂 Music Library: {MUSIC_DIR}")
    print(f"📋 Playlists:     {PLAYLIST_DIR}")
    print(f"🌐 Web UI:       http://{args.host}:{args.port}")

    try:
        ip = socket.gethostbyname(socket.gethostname())
        print(f"📡 Network:      http://{ip}:{args.port}")
    except Exception:
        print(f"🌐 Local:        http://localhost:{args.port}")

    print(f"💻 Platform:     {platform.system()} {platform.release()}")
    print(f"⚠️  Ensure your firewall allows port {args.port}")
    print()

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)