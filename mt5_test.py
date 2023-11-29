import os
import dotenv
import MetaTrader5 as mt5

dotenv.load_dotenv()

MT5_SERVER = os.environ["MT5_SERVER"]
MT5_LOGIN = os.environ["MT5_LOGIN"]
MT5_PASSWORD = os.environ["MT5_PASSWORD"]
MT5_PATH = os.environ["MT5_PATH"]
DATA_PATH = os.environ["DATA_PATH"]
CATALOG_PATH = os.environ["CATALOG_PATH"]

print(type(MT5_SERVER))
print(type(MT5_LOGIN))
print(type(MT5_PASSWORD))
print(type(MT5_PATH))
print(MT5_PATH)

if not mt5.initialize():
    print("ERROR: initialize() failed")
    mt5.shutdown()
    quit()

info = mt5.terminal_info()
account_info = mt5.account_info()

print(info)
print(account_info)
