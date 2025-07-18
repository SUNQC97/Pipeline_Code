from opcua import Server, ua
from dotenv import load_dotenv
import os
import json



def start_opc_server_with_trafo(param_names=None, param_values=None):
    """
    启动 OPC UA Server，并将 trafo 参数写入 Config 节点中的 TrafoConfigJSON。
    """
    dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))
    load_dotenv(dotenv_path)

    host = os.getenv("OPC_SERVER_HOST", "0.0.0.0")
    port = os.getenv("OPC_SERVER_PORT", "4840")
    url = f"opc.tcp://{host}:{port}"

    # 初始化 Server
    server = Server()
    server.set_endpoint(url)
    server.set_server_name("TwinCAT OPC UA Server")
    idx = server.register_namespace("http://example.org/")

    # 创建 Config 节点
    objects = server.get_objects_node()
    config_obj = objects.add_object(idx, "Config")

    # 添加 TrafoConfigJSON 可写变量（如果传入了参数）
    if param_names and param_values:
        data = {
            "param_names": param_names,
            "param_values": param_values
        }
        json_str = json.dumps(data)

        json_node = config_obj.add_variable(
            idx, "TrafoConfigJSON", json_str, varianttype=ua.VariantType.String
        )
        json_node.set_writable()
        print("TrafoConfigJSON 已写入 OPC UA 节点")

    # 示例变量（可选）
    example_node = config_obj.add_variable(
        idx, "ExampleVar", "test", varianttype=ua.VariantType.String
    )
    example_node.set_writable()

    print(f"OPC UA Server started at {url}")
    server.start()

    return server


def stop_opc_server(server):
    if server:
        server.stop()
        print("OPC UA Server stopped.")
    else:
        print("No server instance to stop.")

    return server

