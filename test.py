from lib.utils.xml_read_write import change_xml_from_new_kanal
from lib.utils.save_to_file import save_kanal_xml_to_file

with open("D:\\Masterarbeit\\Temp_xml_Datei\\Kanal_1.xml", "r", encoding="utf-8") as f:
    xml_data = f.read()

# 修改 XML（自动读取 .env 中的 .lis 文件）
new_xml = change_xml_from_new_kanal(xml_data)

# 保存结果到 Temp_Datei/Kanal_1.xml
save_kanal_xml_to_file(new_xml, "Kanal_1")
