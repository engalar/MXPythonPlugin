#!/usr/bin/env python3
import os
import subprocess
import json
from typing import Dict, List

def get_changed_files_by_plugin() -> Dict[str, List[str]]:
    """
    使用 git status，返回一个字典，键是插件目录，值是该目录下已更改的文件路径列表。
    """
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            check=True
        )
        
        if not result.stdout.strip():
            return {}

        files_by_dir: Dict[str, List[str]] = {}
        for line in result.stdout.strip().split('\n'):
            path = line.strip().split(maxsplit=1)[-1].strip('"')
            dir_name = os.path.dirname(path)

            if dir_name and os.sep not in dir_name and dir_name != '.':
                if dir_name not in files_by_dir:
                    files_by_dir[dir_name] = []
                files_by_dir[dir_name].append(path)
                
        return files_by_dir

    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: 'git' 命令执行失败。请确保您在 git 仓库中，并且已安装 git。")
        return {}

def process_plugin(directory: str, changed_files: List[str]):
    """
    根据插件目录及其变更文件列表，生成创建或更新命令。
    """
    manifest_path = os.path.join(directory, 'manifest.json')

    if not os.path.isfile(manifest_path):
        return

    print(f"--- Plugin: {directory} ---")

    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"无法读取或解析 '{manifest_path}': {e}\n")
        return

    home_url = manifest_data.get('home')

    if home_url:
        # --- 更新逻辑 (最终修正版) ---
        # 事实证明 gh gist edit 一次只能处理一个文件更新。
        # 因此，为每个变动的文件生成一条独立的命令。
        try:
            gist_id = home_url.split('/')[-1]
            if not gist_id:
                raise ValueError("无法从URL中解析Gist ID")
            
            print("# Action: UPDATE existing Gist (为每个变动的文件生成单独的命令)")
            
            # 遍历每一个变动的文件
            for f in changed_files:
                basename = os.path.basename(f)
                # 为该文件生成一条完整的、独立的命令
                print(f'gh gist edit {gist_id} "{f}" -f "{basename}"')
                
        except (IndexError, ValueError):
            print(f"错误: 'home' URL '{home_url}' 无效。无法提取 Gist ID。")
    else:
        # --- 创建逻辑 (此逻辑是正确的, gh gist create 支持多文件) ---
        print("# Action: CREATE new Gist (上传插件的所有文件)")
        
        all_plugin_files: List[str] = [manifest_path]
        
        ui_file = manifest_data.get('ui')
        if ui_file and os.path.isfile(os.path.join(directory, ui_file)):
            all_plugin_files.append(os.path.join(directory, ui_file))
        
        plugin_file = manifest_data.get('plugin')
        if plugin_file and os.path.isfile(os.path.join(directory, plugin_file)):
            all_plugin_files.append(os.path.join(directory, plugin_file))

        readme_path = os.path.join(directory, 'README.md')
        if os.path.isfile(readme_path):
            all_plugin_files.append(readme_path)
            
        description = manifest_data.get('description', f'Plugin: {directory}')
        files_to_create_str = ' '.join(f'"{f}"' for f in all_plugin_files)
        
        print(f'gh gist create {files_to_create_str} -p --desc "{description}"')
        print(f"# 注意：创建成功后，请将新的 Gist URL 手动添加到 '{manifest_path}' 的 'home' 字段中。")
    
    print("")

def main():
    """脚本主入口"""
    print("#####################################################################")
    print("# 根据 git 文件变动，生成精确的 gh gist 创建或更新命令          #")
    print("# 请手动复制并执行您需要的命令                                    #")
    print("#####################################################################")
    print("")

    changed_files_map = get_changed_files_by_plugin()

    if not changed_files_map:
        print("没有检测到任何文件变更。工作区是干净的。")
        return

    for directory, changed_files in sorted(changed_files_map.items()):
        process_plugin(directory, changed_files)
    
    print("---")
    print("命令生成完毕。")

if __name__ == "__main__":
    main()