import json
import os

TEMP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..","..","Temp_Datei"))

def save_structure_to_file(structure: dict, filename: str):
    """
    保存结构为 JSON 文件（固定文件名，存到 Temp_Datei 文件夹）
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    filepath = os.path.join(TEMP_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(structure, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved structure to {filepath}")
    return filepath


def load_structure_from_file(filename: str) -> dict:
    """
    从 Temp_Datei 文件夹读取 JSON 文件
    """
    filepath = os.path.join(TEMP_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
    
def save_xml_to_file(xml_data, Name: str):
    """
    保存 Kanal 的 XML 数据到文件
    """
    TEMP_DIR_XML = TEMP_DIR+ "/XML_Datei" 
    filename = f"{Name}.xml"
    filepath = os.path.join(TEMP_DIR_XML, filename)

    os.makedirs(TEMP_DIR_XML, exist_ok=True)  # 确保目标文件夹存在
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(xml_data)

    print(f"[OK] Saved XML for {Name} to {filepath}")
    return filepath

def save_opcua_data_to_file(kanal_data_dict):
    """
    将 OPC UA 原始 JSON 数据直接保存为文件（不做结构转换）。
    每个 Kanal 会保存：
    """
    TEMP_DIR_OPCUA = os.path.join(TEMP_DIR, "OPCUA_Datei")

    os.makedirs(TEMP_DIR_OPCUA, exist_ok=True)

    for kanal_name, data in kanal_data_dict.items():
        kanal_dir = os.path.join(TEMP_DIR_OPCUA, kanal_name)
        os.makedirs(kanal_dir, exist_ok=True)

        # directly use the JSON content from the data
        trafo_content = data.get("TrafoConfigJSON", "{}")
        axis_content = data.get("AxisConfigJSON", "{}")

        # 支持既可为 dict，也可为字符串的情况
        if isinstance(trafo_content, str):
            trafo_parsed = json.loads(trafo_content)
        else:
            trafo_parsed = trafo_content

        if isinstance(axis_content, str):
            axis_parsed = json.loads(axis_content)
        else:
            axis_parsed = axis_content

        with open(os.path.join(kanal_dir, "TrafoConfigJSON.json"), "w", encoding="utf-8") as f:
            json.dump(trafo_parsed, f, indent=2, ensure_ascii=False)

        with open(os.path.join(kanal_dir, "AxisConfigJSON.json"), "w", encoding="utf-8") as f:
            json.dump(axis_parsed, f, indent=2, ensure_ascii=False)

        print(f"[OK] Raw OPC UA JSON saved for {kanal_name} in {kanal_dir}")