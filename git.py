import subprocess
from datetime import date

def git_commands():
    try:
        # 获取今天的日期
        today_str = date.today().isoformat()
        commit_message = f"update {today_str}"

        # 查看 Git 状态
        subprocess.run(['git', 'status'], check=True)

        # 添加所有更改
        subprocess.run(['git', 'add', '.'], check=True)

        # 提交更改
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)

        # 使用 --force-with-lease 更安全的强制推送
        print("[INFO] Force pushing with lease (safer)...")
        subprocess.run(['git', 'push', '--force-with-lease', 'origin', 'main'], check=True)

        print(f"[OK] Force committed and pushed with message: {commit_message}")
    
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git command failed: {e}")

# 执行 Git 命令
git_commands()