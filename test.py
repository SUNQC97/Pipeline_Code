from lib.utils.xml_read_write import change_xml_from_new_axis
from lib.utils.save_to_file import save_xml_to_file

with open("D:\Masterarbeit\Temp_xml_Datei\Axis_12.xml", "r", encoding="utf-8") as f:
    xml_data = f.read()

# 修改 XML（自动读取 .env 中的 .lis 文件）
new_xml = change_xml_from_new_axis(xml_data, "Axis_12", "Kanal_2")

# 保存结果到 Temp_Datei/Axis_1.xml
save_xml_to_file(new_xml, "Axis_12")
