from lib.services import Virtuos_tool, remote, server
import os
from dotenv import load_dotenv

initialized = False
vz_env = None
vz = None

vz_env = Virtuos_tool.VirtuosEnv()
vz = vz_env.vz
vz.virtuosDLL()
vz.corbaInfo()
vz.startConnectionCorba()

if vz.isOpen() == vz.V_DAMGD:
    print("Virtuos or the desired project did not start.")  
else:
    print("Virtuos is open, proceeding with project loading.")
    vz.getProject(os.getenv("project_path"))

    if vz.isOpen() == vz.V_DAMGD:
        print("Failed to load the project.")
    else:
        initialized = True
        print("Virtuos environment initialized successfully.")

param_names, param_values = Virtuos_tool.extract_trafo_param_list(vz, "[Block Diagram].[RobotController]")

server.start_opc_server_with_trafo(param_names, param_values)
