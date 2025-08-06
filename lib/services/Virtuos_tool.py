from . import remote
import os
from dotenv import load_dotenv
import re

dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
load_dotenv(dotenv_path)

project_path = os.getenv("project_path")
controller_path = os.getenv("extract_controller_path")

class VirtuosEnv:
    def __init__(self):
        """
        Initializes the Virtuos environment and creates a VirtuosZugriff object.

        Sets up the Virtuos environment by creating a VirtuosZugriff object and initializes
        the Virtuos environment. This is necessary to interact with the Virtuos environment
        and execute the various configurations.

        Attributes:
            vz: VirtuosZugriff object
        """
        self.vz = remote.VirtuosZugriff()
        print("VirtuosEnv initialized")

    def connect_to_virtuos(self):
        """
        Asynchronously initializes the Virtuos environment and establishes a connection.

        This function creates an instance of the Virtuos environment and connects to Virtuos
        asynchronously. It returns the VirtuosZugriff object and the Virtuos environment object.

        Returns:
            tuple: A tuple containing the VirtuosZugriff object and the Virtuos environment object.
        """
        try:

            # Establish connection to remote DLL
            self.vz.virtuosDLL()
            
            # Start Virtuos
            startVirtuosResult = self.vz.startVirtuosExe()
            if startVirtuosResult != self.vz.V_SUCCD:
                raise Exception("Error starting ISG-virtuos")
            
            # Initialize Corba server info
            setCorbaInfoResult = self.vz.corbaInfo()
            if setCorbaInfoResult == self.vz.V_SUCCD:
                startConnectionResult =self.vz.startConnectionCorba()
                if startConnectionResult == self.vz.V_SUCCD:
                    print("Connection to Corba server established.")
                else:
                    raise Exception("Failed to connect to Corba server.")

        
            # Check if Virtuos is open
            if self.vz.isOpen() == self.vz.V_DAMGD:
                raise Exception("Virtuos or the desired project did not start.")
                         
            loadProjectResult = self.vz.getProject(project_path)
            if loadProjectResult != self.vz.V_SUCCD:
                raise Exception("Error loading ISG-virtuos project")
            
            # # Interpret a JavaScript file
            # if self.vz.interpretJSFileFn("..\\assets\\Tree.js") != self.vz.V_SUCCD:
            #     raise Exception("Error interpreting JS file")

            print("Virtuos environment initialized successfully")
            return self.vz  # Return the VirtuosZugriff object for use in the GUI
                        
        except Exception as e:
            print(f"Exception occurred: {e}")
            return None

    def disconnect(self):
        """
        Disconnects from the Virtuos environment and unloads the DLL.

        This method disconnects from the Virtuos environment and unloads the DLL. It is
        called when the GUI is closed or when the user clicks the Disconnect button.

        Exceptions that are raised during the disconnect process are caught and printed to
        the console.

        Returns:
            None
        """
        try:
            self.vz.stopVirtuosPrgm()
            self.vz.stopConnect()
            self.vz.unloadDLL()
            print("Virtuos disconnected successfully")
        except Exception as e:
            print(f"Exception occurred during disconnect: {e}")



def read_value_model(vz, parameter_path: str):

    if not vz:
        print("Virtuos not connected.")
        return
    Parameter_Value = vz.getParameterBlock_New(parameter_path)
    return Parameter_Value


def read_Value_Model_json(vz, parameter_path: str):
    trafo_params = {}
    axis_params = {}

    # 读取 KinID
    try:
        kinid_path = f"{parameter_path}.[KinID]"
        kinid_value = vz.getParameterBlock_New(kinid_path)
        if kinid_value is not None:
            trafo_params["trafo[0].id"] = kinid_value
        else:
            print(f"KinID not found at {kinid_path}")
    except Exception as e:
        print(f"Error reading KinID: {e}")


        # 读取 trafo 参数
    for i in range(9999):
        full_path = f"{parameter_path}.[par_{i}]"
        try:
            Parameter_Value = vz.getParameterBlock_New(full_path)
            if Parameter_Value is None:
                break
            trafo_params[f"trafo[0].param[{i}]"] = Parameter_Value
        except Exception as e:
            print(f"Error reading parameter {full_path}: {e}")
            break

    # 读取 Axis 参数
    param_prefix_groups = {
            "Axis": ["ratio", "s_min", "s_max", "s_init", "v_max", "a_max"],
            "Ext":  ["ratio", "s_min", "s_max", "s_init", "v_max", "a_max"],
            # 可继续添加其他组
        }

    for prefix, fields in param_prefix_groups.items():
        for index in range(1, 99):  # 假设最多99个
            for field in fields:
                full_key = f"{parameter_path}.[{prefix}_{index}.{field}]"
                try:
                   value = vz.getParameterBlock_New(full_key)
                   if value is not None:
                      axis_params[f"{prefix}_{index}.{field}"] = value
                except Exception as e:
                    print(f"Error reading {full_key}: {e}")

    return trafo_params, axis_params


def extract_trafo_param_list(vz, parameter_path):
    trafo_params, _ = read_Value_Model_json(vz, parameter_path)
    names = list(trafo_params.keys())
    values = list(trafo_params.values())
    return names, values

def extract_axis_param_list(axis_params: dict):
    param_names = list(axis_params.keys())
    param_values = list(axis_params.values())
    return param_names, param_values

def write_params_to_virtuos(vz, parameter_path, trafo_names, trafo_values, axis_names, axis_values):
    for name, value in zip(trafo_names, trafo_values):
        converted_name = convert_param_name_for_write(name)
        write_single_param_to_virtuos(vz, parameter_path, converted_name, value)
    for name, value in zip(axis_names, axis_values):
        converted_name = convert_param_name_for_write(name)
        write_single_param_to_virtuos(vz, parameter_path, converted_name, value)

def write_single_param_to_virtuos(vz, parameter_path: str, param_name: str, param_value):
    """
    Write parameter from opcua to Virtuos.
    """
    try:
        full_path = make_virtuos_param_path(parameter_path, param_name)
        value_str = str(param_value)  # 必须是字符串
        status = vz.setParameterBlock(full_path, value_str)
        if status == vz.V_SUCCD:
            #print(f"[OK] Wrote {full_path} = {value_str}")
            return True
        else:
            print(f"[ERROR] Failed to write {full_path} (status: {status})")
            return False
    except Exception as e:
        print(f"[EXCEPTION] Failed to write {param_name} to Virtuos: {e}")
        return False
    
def make_virtuos_param_path(base_path: str, param_name: str) -> str:
    """
    Create a full parameter path for Virtuos based on the base path and parameter name.
    """
    return f"{base_path}.[{param_name}]"

def convert_param_name_for_write(param_name: str) -> str:
    # Trafo: trafo[0].id → KinID
    if param_name == "trafo[0].id":
        return "KinID"

    # Trafo: trafo[0].param[5] → par_5
    if param_name.startswith("trafo[0].param["):
        index = param_name[len("trafo[0].param["):-1]
        return f"par_{index}"

    # Axis/Ext: 保持原样，如 Axis_1.s_max → Axis_1.s_max
    return param_name




def load_block_map() -> dict:
    """
    Load the block map from the file specified by the environment variable BLOCK_MAP_PATH.

    It parses only the 'Model uuids' section, and returns a dictionary that maps
    block names (with and without brackets) to their full block diagram paths.

    Example:
        "RobotController" -> "[Block Diagram].[RobotController]"
        "[RobotController]" -> "[Block Diagram].[RobotController]"

    Returns:
        dict: {block_name: full_path}
    """
    if not controller_path or not os.path.isfile(controller_path):
        raise FileNotFoundError(f"BLOCK_MAP_PATH not found or invalid: {controller_path}")

    block_path_dict = {}
    in_model_section = False

    with open(controller_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()

            # Start capturing from the "Model uuids" section
            if line.startswith("//Model uuids"):
                in_model_section = True
                continue
            elif line.startswith("//Port uuids"):  # stop when Port uuids start
                break

            if in_model_section:
                # Match = [Block Diagram].[xxx].[yyy] ;
                match = re.search(r'=\s*(\[[^\]]+\](?:\.\[[^\]]+\])*)\s*;', line)
                if match:
                    full_path = match.group(1)
                    block_name = full_path.split('.')[-1].strip('[]')
                    block_path_dict[block_name] = full_path
                    block_path_dict[f'[{block_name}]'] = full_path  # for names with brackets

    return block_path_dict


def get_block_path(block_name: str, block_map: dict) -> str:
    """
    Get the full block path from a given block name.

    Args:
        block_name (str): The name of the block, with or without brackets.
        block_map (dict): A dictionary returned by `load_block_map`.

    Returns:
        str: The full block path, or "Not Found" if it does not exist.
    """
    return block_map.get(block_name.strip(), "Not Found")