from opcua import Server, ua
import json
import os
from dotenv import load_dotenv
from lib.services import remote  # 替换为你真实的模块名
from lib.services import Virtuos_tool  # 替换路径
from lib.services import server

# === 初始化环境变量 ===
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
load_dotenv(dotenv_path)
host = os.getenv("SERVER_IP", "localhost")
port = os.getenv("SERVER_PORT", "4840")
project_path = os.getenv("project_path")

# === 初始化 Virtuos 连接（已打开的项目） ===
initialized = False
vz_env = Virtuos_tool.VirtuosEnv()
vz = vz_env.vz

vz.virtuosDLL()
vz.corbaInfo()
vz.startConnectionCorba()

if vz.isOpen() == vz.V_SUCCD:
    print("[OK] Connected to already open Virtuos project.")
else:
    status = vz.getProject(project_path)
    if status == vz.V_SUCCD:
        print("[OK] Project loaded and connected.")
    else:
        print("[ERROR] No open project and failed to load.")
        exit(1)

initialized = True

# === 读取 Trafo 和 Axis 参数 ===
parameter_path = "[Block Diagram].[RobotController]"  # 替换为你实际路径
trafo_params, axis_params = Virtuos_tool.read_Value_Model_json(vz, parameter_path)


server.create_opc_server()



try:
    input("Press Enter to stop server...\n")
finally:
    server.stop()
    vz.stopVirtuosPrgm()
    vz.stopConnect()
    vz.unloadDLL()
    print("[STOPPED] Server + Virtuos closed.")