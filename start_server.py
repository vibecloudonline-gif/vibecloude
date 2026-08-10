import uvicorn
import main
import sys
import logging

logging.basicConfig(level=logging.DEBUG)

if __name__ == "__main__":
    try:
        uvicorn.run(main.app, host="127.0.0.1", port=8124, log_level="debug")
    except Exception as e:
        import traceback
        traceback.print_exc(file=open("server_crash.txt", "w"))
