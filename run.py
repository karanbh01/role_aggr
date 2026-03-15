"""
Entry point for role/aggr.

Starts uvicorn bound to 0.0.0.0 so any device on your local network
can access the app. Prints the local IP address for convenience.
"""

import socket
import uvicorn
from config import HOST, PORT


def get_local_ip() -> str:
    """Get this machine's local network IP address."""
    try:
        # Connect to an external address to determine the local IP
        # (doesn't actually send data)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    local_ip = get_local_ip()
    print()
    print("  +----------------------------------------------+")
    print("  |            role/aggr v2                       |")
    print("  +----------------------------------------------+")
    local_addr = f"http://localhost:{PORT}"
    print(f"  |  Local:   {local_addr:<33s}|")
    network_addr = f"http://{local_ip}:{PORT}"
    print(f"  |  Network: {network_addr:<33s}|")
    print("  +----------------------------------------------+")
    print()

    uvicorn.run(
        "app:app",
        host=HOST,
        port=PORT,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
