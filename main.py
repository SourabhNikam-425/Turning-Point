import asyncio
import sys

from src.turning_point.agent import run_agent


if __name__ == "__main__":
    if "--web" in sys.argv or "-w" in sys.argv or "--gui" in sys.argv:
        from src.turning_point.server import run_web_server
        run_web_server()
    else:
        asyncio.run(run_agent())