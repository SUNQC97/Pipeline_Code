import subprocess

def git_commands():
    try:
        # 查看 Git 状态
        subprocess.run(['git', 'status'], check=True)

        # 添加所有更改
        subprocess.run(['git', 'add', '.'], check=True)

        # 提交更改
        subprocess.run(['git', 'commit', '-m', 'update'], check=True)

        # 推送更改到 GitHub
        subprocess.run(['git', 'push', 'origin', 'main'], check=True)

        print("Code has been successfully committed and pushed to GitHub.")
    
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")

# 执行 Git 命令
    
git_commands()


