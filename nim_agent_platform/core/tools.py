import os
import subprocess
import json
import glob
from pathlib import Path

# Sibling directory path for agent-skills
SKILLS_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'agent-skills'))
SKILLS_DIR = os.path.join(SKILLS_ROOT, 'skills')

# Define schemas for NVIDIA NIM / OpenAI tool calling
AGENT_TOOLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Lists the files and folders in the active workspace. Useful to explore files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "The folder path relative to the workspace root. Default is root (empty string).",
                    }
                },
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads the content of a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Path to the file relative to the workspace root.",
                    }
                },
                "required": ["relative_path"],
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Writes or updates a file in the workspace with the specified content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Path to the file relative to the workspace root.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content to write to the file.",
                    }
                },
                "required": ["relative_path", "content"],
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Runs a terminal command in the workspace directory. Use to run tests (e.g. pytest), build scripts, formatters, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact shell command to execute in the workspace directory.",
                    }
                },
                "required": ["command"],
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": "Searches for keywords in the agent skills repository to find which skills are available and their details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search keyword (e.g., 'test', 'review', 'simplify').",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": "Reads the full details of an agent skill from the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "The kebab-case name of the skill (e.g., 'test-driven-development').",
                    }
                },
                "required": ["skill_name"],
                "additionalProperties": False,
            }
        }
    }
]

# Helper to ensure sandbox constraints
def get_safe_path(workspace_root, relative_path):
    # Standardize path separators and resolve relative directories
    safe_root = Path(workspace_root).resolve()
    target_path = Path(os.path.join(workspace_root, relative_path)).resolve()
    
    # Check if target_path is within safe_root
    if safe_root not in target_path.parents and target_path != safe_root:
        raise ValueError(f"Path escape detected: {relative_path} is outside of workspace root.")
    
    return str(target_path)

def ensure_workspace_exists(workspace_path):
    if not os.path.exists(workspace_path):
        os.makedirs(workspace_path, exist_ok=True)


# Tool executors
def execute_list_dir(workspace_root, relative_path=""):
    try:
        target_dir = get_safe_path(workspace_root, relative_path or "")
        ensure_workspace_exists(target_dir)
        
        items = os.listdir(target_dir)
        result = []
        for item in items:
            full_path = os.path.join(target_dir, item)
            is_dir = os.path.isdir(full_path)
            size = os.path.getsize(full_path) if not is_dir else "-"
            result.append({
                "name": item,
                "type": "directory" if is_dir else "file",
                "size": size
            })
        return json.dumps({"status": "success", "files": result}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def execute_read_file(workspace_root, relative_path):
    try:
        target_file = get_safe_path(workspace_root, relative_path)
        if not os.path.exists(target_file):
            return json.dumps({"status": "error", "message": f"File does not exist: {relative_path}"})
        
        if os.path.isdir(target_file):
            return json.dumps({"status": "error", "message": f"Path is a directory, not a file: {relative_path}"})
            
        with open(target_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return json.dumps({"status": "success", "content": content})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def execute_write_file(workspace_root, relative_path, content):
    try:
        target_file = get_safe_path(workspace_root, relative_path)
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return json.dumps({"status": "success", "message": f"Successfully wrote {len(content)} characters to {relative_path}"})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def execute_run_command(workspace_root, command):
    try:
        ensure_workspace_exists(workspace_root)
        
        # Block malicious commands if necessary, but since this is local and user approved, we run it
        # Setting timeout to 30 seconds to prevent hangs
        result = subprocess.run(
            command,
            shell=True,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout + "\n" + result.stderr
        return json.dumps({
            "status": "success",
            "exit_code": result.returncode,
            "output": output
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "error", "message": "Command timed out after 30 seconds."})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def execute_search_skills(query):
    try:
        if not os.path.exists(SKILLS_DIR):
            return json.dumps({"status": "error", "message": f"Skills directory not found at {SKILLS_DIR}"})
        
        matches = []
        # Search SKILL.md files in all skills subdirectories
        for skill_folder in os.listdir(SKILLS_DIR):
            folder_path = os.path.join(SKILLS_DIR, skill_folder)
            if not os.path.isdir(folder_path):
                continue
                
            skill_md_path = os.path.join(folder_path, 'SKILL.md')
            if os.path.exists(skill_md_path):
                with open(skill_md_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    if query.lower() in content.lower() or query.lower() in skill_folder.lower():
                        # Extract description from frontmatter if possible
                        desc = "No description found"
                        lines = content.split('\n')
                        for line in lines:
                            if line.startswith('description:'):
                                desc = line.replace('description:', '').strip()
                                break
                        matches.append({
                            "name": skill_folder,
                            "description": desc
                        })
        return json.dumps({"status": "success", "results": matches})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def execute_read_skill(skill_name):
    try:
        # Standardize skill name to clean up relative paths
        skill_name = os.path.basename(skill_name)
        skill_md_path = os.path.join(SKILLS_DIR, skill_name, 'SKILL.md')
        
        if not os.path.exists(skill_md_path):
            return json.dumps({"status": "error", "message": f"Skill '{skill_name}' not found."})
            
        with open(skill_md_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            
        return json.dumps({"status": "success", "skill_name": skill_name, "content": content})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


# Dispatcher
def dispatch_tool_call(session, function_name, arguments_dict):
    workspace_root = session.get_actual_workspace()
    ensure_workspace_exists(workspace_root)
    
    if function_name == "list_dir":
        return execute_list_dir(workspace_root, arguments_dict.get("relative_path", ""))
    elif function_name == "read_file":
        return execute_read_file(workspace_root, arguments_dict.get("relative_path"))
    elif function_name == "write_file":
        return execute_write_file(workspace_root, arguments_dict.get("relative_path"), arguments_dict.get("content"))
    elif function_name == "run_command":
        return execute_run_command(workspace_root, arguments_dict.get("command"))
    elif function_name == "search_skills":
        return execute_search_skills(arguments_dict.get("query"))
    elif function_name == "read_skill":
        return execute_read_skill(arguments_dict.get("skill_name"))
    else:
        return json.dumps({"status": "error", "message": f"Unknown tool name: {function_name}"})
