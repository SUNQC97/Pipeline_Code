import subprocess, json

def get_all_adapters():
    ps = (
        "Get-NetAdapter | "
        "Select-Object Name, InterfaceDescription, InterfaceGuid, MacAddress | "
        "ConvertTo-Json -Compress"
    )

    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            encoding="utf-8"
        )
    except UnicodeDecodeError:
        # Chinese Windows fallback to GBK
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            encoding="gbk"
        )

    adapters = json.loads(out)
    if isinstance(adapters, dict):
        adapters = [adapters]

    return [
        {
            "Name": f"{a.get('Name')} ({a.get('InterfaceDescription')})", 
            "MAC": a.get("MacAddress"), 
            "GUID": a.get("InterfaceGuid")
        }
        for a in adapters
    ]


if __name__ == "__main__":
    adapters = get_all_adapters()
    print(json.dumps(adapters, indent=2, ensure_ascii=False))
