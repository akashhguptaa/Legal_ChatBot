import os
from dotenv import load_dotenv
from loguru import logger

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path, override=True)

logger.info("Attempting to load environment variables from .env file...")

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path, override=True)
    logger.info(f"Environment variables loaded from {dotenv_path}")

missing_vars = []

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")

if not OPENAI_API_KEY:
    missing_vars.append("OPENAI_API_KEY")
if not MONGODB_URI:
    missing_vars.append("MONGODB_URI")  

if missing_vars:
    logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
    raise EnvironmentError(f"Missing environment variables: {', '.join(missing_vars)}")
else:
    logger.info("All required environment variables are set.")
