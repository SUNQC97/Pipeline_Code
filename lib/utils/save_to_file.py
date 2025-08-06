import json
import os

TEMP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Temp_Datei"))

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