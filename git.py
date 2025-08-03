import subprocess
from datetime import date

def git_commands():
    try:
        # 获取今天的日期
        today_str = date.today().isoformat()  # 格式为 YYYY-MM-DD，例如 2025-08-03
        commit_message = f"update {today_str}"

        # 查看 Git 状态
        subprocess.run(['git', 'status'], check=True)

        # 添加所有更改
        subprocess.run(['git', 'add', '.'], check=True)

        # 提交更改
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)

        # 推送更改到 GitHub
        subprocess.run(['git', 'push', 'origin', 'main'], check=True)

        print(f"[OK] Committed and pushed with message: {commit_message}")
    
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git command failed: {e}")

# 执行 Git 命令
git_commands()
