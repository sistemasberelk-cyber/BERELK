import logging
import os
from pythonjsonlogger import jsonlogger

def setup_logging():
    handlers = []
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    
    try:
        os.makedirs('logs', exist_ok=True)
        logHandler = logging.FileHandler(filename='logs/vibecloud.log')
        logHandler.setFormatter(formatter)
        handlers.append(logHandler)
    except Exception:
        pass  # File logging not available (e.g. read-only filesystem on Render)
    
    streamHandler = logging.StreamHandler()
    streamHandler.setFormatter(formatter)
    handlers.append(streamHandler)
    
    logging.basicConfig(level=logging.INFO, handlers=handlers)
