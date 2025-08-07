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