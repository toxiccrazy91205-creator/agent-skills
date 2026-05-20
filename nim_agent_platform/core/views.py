import os
import json
import markdown
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from openai import OpenAI

from .models import Configuration, Session, Message
from .tools import AGENT_TOOLS_SCHEMAS, dispatch_tool_call, SKILLS_DIR, ensure_workspace_exists

def get_skills_list():
    skills = []
    if os.path.exists(SKILLS_DIR):
        for name in os.listdir(SKILLS_DIR):
            folder = os.path.join(SKILLS_DIR, name)
            if not os.path.isdir(folder):
                continue
            skill_md = os.path.join(folder, 'SKILL.md')
            if os.path.exists(skill_md):
                # Simple extraction of description
                desc = "No description available"
                try:
                    with open(skill_md, 'r', encoding='utf-8', errors='replace') as f:
                        lines = f.readlines()
                        for line in lines:
                            if line.startswith('description:'):
                                desc = line.replace('description:', '').strip()
                                break
                except Exception:
                    pass
                skills.append({
                    'name': name,
                    'title': name.replace('-', ' ').title(),
                    'description': desc
                })
    return skills

def dashboard(request):
    config = Configuration.get_sole_config()
    sessions = Session.objects.all().order_by('-created_at')
    skills = get_skills_list()
    
    # Try listing files in base workspace
    workspace_files_count = 0
    workspace_exists = False
    if config.workspace_path:
        workspace_exists = os.path.exists(config.workspace_path)
        if workspace_exists:
            try:
                # Count files recursively
                for root, dirs, files in os.walk(config.workspace_path):
                    workspace_files_count += len(files)
            except Exception:
                pass

    context = {
        'config': config,
        'sessions_count': sessions.count(),
        'active_sessions_count': sessions.filter(status='running').count(),
        'skills_count': len(skills),
        'workspace_files_count': workspace_files_count,
        'workspace_exists': workspace_exists,
        'recent_sessions': sessions[:5],
    }
    return render(request, 'core/dashboard.html', context)

def settings_view(request):
    config = Configuration.get_sole_config()
    message = None
    message_type = "success"

    if request.method == "POST":
        action = request.POST.get('action')
        if action == "save":
            config.nvidia_api_key = request.POST.get('nvidia_api_key', '').strip()
            config.model_name = request.POST.get('model_name', 'meta/llama-3.3-70b-instruct').strip()
            config.workspace_path = request.POST.get('workspace_path', '').strip()
            config.save()
            message = "Settings saved successfully."
        elif action == "test_connection":
            api_key = request.POST.get('nvidia_api_key', '').strip()
            model = request.POST.get('model_name', 'meta/llama-3.3-70b-instruct').strip()
            
            if not api_key:
                message = "API Key is required to test connection."
                message_type = "error"
            else:
                try:
                    client = OpenAI(
                        api_key=api_key,
                        base_url="https://integrate.api.nvidia.com/v1"
                    )
                    # Use a minimal test call
                    response = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": "Ping"}],
                        max_tokens=10,
                        temperature=0.1
                    )
                    message = f"Connection successful! Model response: '{response.choices[0].message.content.strip()}'"
                    message_type = "success"
                except Exception as e:
                    message = f"Connection failed: {str(e)}"
                    message_type = "error"

    context = {
        'config': config,
        'message': message,
        'message_type': message_type,
    }
    return render(request, 'core/settings.html', context)

def skills_list(request):
    skills = get_skills_list()
    query = request.GET.get('q', '').strip()
    if query:
        skills = [s for s in skills if query.lower() in s['name'].lower() or query.lower() in s['description'].lower()]
        
    context = {
        'skills': skills,
        'query': query
    }
    return render(request, 'core/skills_list.html', context)

def skills_detail(request, skill_name):
    skill_md_path = os.path.join(SKILLS_DIR, skill_name, 'SKILL.md')
    if not os.path.exists(skill_md_path):
        return redirect('skills_list')
        
    content_html = ""
    title = skill_name.replace('-', ' ').title()
    try:
        with open(skill_md_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            # Strip YAML frontmatter if present
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    content = parts[2]
            content_html = markdown.markdown(content, extensions=['fenced_code', 'tables'])
    except Exception as e:
        content_html = f"<p>Error rendering markdown: {str(e)}</p>"
        
    context = {
        'skill_name': skill_name,
        'title': title,
        'content_html': content_html
    }
    return render(request, 'core/skills_detail.html', context)

def session_list(request):
    sessions = Session.objects.all().order_by('-created_at')
    return render(request, 'core/session_list.html', {'sessions': sessions})

def session_create(request):
    if request.method == "POST":
        title = request.POST.get('title', '').strip()
        skill_name = request.POST.get('skill_name', '').strip()
        user_prompt = request.POST.get('user_prompt', '').strip()
        
        if not title or not skill_name or not user_prompt:
            return render(request, 'core/session_create.html', {
                'error': 'All fields are required.',
                'skills': get_skills_list()
            })
            
        # Get skill details for system prompt
        skill_details = ""
        skill_md_path = os.path.join(SKILLS_DIR, skill_name, 'SKILL.md')
        if os.path.exists(skill_md_path):
            try:
                with open(skill_md_path, 'r', encoding='utf-8', errors='replace') as f:
                    skill_details = f.read()
            except Exception:
                pass
                
        session = Session.objects.create(
            title=title,
            skill_name=skill_name,
            status='idle'
        )
        
        # Build standard system prompt incorporating the skill
        system_prompt = (
            "You are a professional, senior software engineer agent utilizing the Nvidia NIM API.\n"
            f"You have been assigned to follow the workflow in the '{skill_name}' skill.\n\n"
            "Here are the instructions and guidelines of the skill you must follow:\n"
            "=====================================================================\n"
            f"{skill_details}\n"
            "=====================================================================\n\n"
            "Operating Rules:\n"
            "1. Ground all choices in real code; do not skip verification steps.\n"
            "2. Make incremental modifications, verifying each change via test running.\n"
            "3. If you run a command to run tests and it fails, triage and recover rather than ignoring the failure.\n"
            "4. Be concise and explain your actions. List the files you are modifying and the commands you run.\n"
            "5. To achieve your tasks, you can use the available tools. Do not output mock content; write real files.\n"
        )
        
        session.system_prompt = system_prompt
        session.save()
        
        # Save initial system and user messages
        Message.objects.create(session=session, role='system', content=system_prompt)
        Message.objects.create(session=session, role='user', content=user_prompt)
        
        return redirect('session_detail', session_id=session.id)
        
    return render(request, 'core/session_create.html', {'skills': get_skills_list()})

def session_detail(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    messages = session.messages.all()
    config = Configuration.get_sole_config()
    
    # Check if API Key is configured
    has_api_key = bool(config.nvidia_api_key)
    
    context = {
        'session': session,
        'messages': messages,
        'has_api_key': has_api_key,
        'model_name': config.model_name,
        'workspace_path': session.get_actual_workspace()
    }
    return render(request, 'core/session_detail.html', context)


@csrf_exempt
@require_POST
def session_step_api(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    config = Configuration.get_sole_config()
    
    if not config.nvidia_api_key:
        return JsonResponse({"status": "error", "message": "NVIDIA API Key is not configured. Go to Settings to set it up."})
        
    # Get last message to see what state we are in
    last_message = session.messages.all().order_by('-created_at', '-id').first()
    
    if not last_message:
        return JsonResponse({"status": "error", "message": "No messages in session."})
        
    # 1. State: Assistant has requested tools, and they need to be executed
    if last_message.role == 'assistant' and last_message.tool_calls:
        # Check if client sent approval to run the tool calls
        try:
            body = json.loads(request.body)
            approved = body.get('approved', False)
        except Exception:
            approved = False
            
        if not approved:
            return JsonResponse({
                "status": "pending_approval", 
                "message": "Tool execution is pending user approval.",
                "tool_calls": last_message.tool_calls
            })
            
        # Execute the tool calls!
        session.status = 'running'
        session.save()
        
        executed_results = []
        for tc in last_message.tool_calls:
            tc_id = tc.get('id')
            func_name = tc.get('function', {}).get('name')
            func_args_str = tc.get('function', {}).get('arguments', '{}')
            
            try:
                # Arguments are sometimes returned as a dict already, or string
                if isinstance(func_args_str, str):
                    func_args = json.loads(func_args_str)
                else:
                    func_args = func_args_str
            except Exception:
                func_args = {}
                
            # Execute the tool!
            result_str = dispatch_tool_call(session, func_name, func_args)
            
            # Save the tool output message in the database
            Message.objects.create(
                session=session,
                role='tool',
                content=result_str,
                tool_call_id=tc_id,
                name=func_name
            )
            executed_results.append({
                "tool_call_id": tc_id,
                "name": func_name,
                "result": result_str
            })
            
        session.status = 'idle'
        session.save()
        
        return JsonResponse({
            "status": "tool_executed",
            "results": executed_results
        })
        
    # 2. State: Last message is user input or tool outputs. We must query the LLM.
    session.status = 'running'
    session.save()
    
    # Load entire conversation history
    messages_query = session.messages.all()
    api_messages = []
    
    for msg in messages_query:
        api_msg = {"role": msg.role, "content": msg.content or ""}
        
        if msg.tool_calls:
            api_msg["tool_calls"] = msg.tool_calls
        if msg.tool_call_id:
            api_msg["tool_call_id"] = msg.tool_call_id
        if msg.name:
            api_msg["name"] = msg.name
            
        api_messages.append(api_msg)
        
    try:
        client = OpenAI(
            api_key=config.nvidia_api_key,
            base_url="https://integrate.api.nvidia.com/v1"
        )
        
        response = client.chat.completions.create(
            model=config.model_name,
            messages=api_messages,
            tools=AGENT_TOOLS_SCHEMAS,
            tool_choice="auto",
            temperature=0.4
        )
        
        response_message = response.choices[0].message
        content = response_message.content or ""
        tool_calls = response_message.tool_calls
        
        # Serialize tool calls if any
        tool_calls_json = None
        if tool_calls:
            tool_calls_json = []
            for tc in tool_calls:
                tool_calls_json.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                })
                
        # Save assistant's response to database
        db_message = Message.objects.create(
            session=session,
            role='assistant',
            content=content,
            tool_calls=tool_calls_json
        )
        
        session.status = 'idle'
        session.save()
        
        if tool_calls_json:
            return JsonResponse({
                "status": "pending_approval",
                "message": "Assistant requested tool execution.",
                "content": content,
                "tool_calls": tool_calls_json
            })
        else:
            # Check if assistant signaled completion (e.g. they say they are done)
            # If they didn't call tools, this turn of conversation is finished
            return JsonResponse({
                "status": "completed",
                "content": content
            })
            
    except Exception as e:
        session.status = 'failed'
        session.save()
        return JsonResponse({"status": "error", "message": f"NVIDIA NIM call failed: {str(e)}"})


def workspace_view(request):
    config = Configuration.get_sole_config()
    session_id = request.GET.get('session_id')
    
    workspace_path = config.workspace_path
    session_obj = None
    if session_id:
        session_obj = get_object_or_404(Session, id=session_id)
        workspace_path = session_obj.get_actual_workspace()
        
    ensure_workspace_exists(workspace_path)
    
    # Handle direct file edits or view requests
    filepath = request.GET.get('file', '').strip()
    file_content = ""
    file_full_path = ""
    if filepath:
        # Resolve safe path
        try:
            from .tools import get_safe_path
            file_full_path = get_safe_path(workspace_path, filepath)
            if os.path.exists(file_full_path) and os.path.isfile(file_full_path):
                with open(file_full_path, 'r', encoding='utf-8', errors='replace') as f:
                    file_content = f.read()
        except Exception:
            pass
            
    # Handle file save POST
    if request.method == "POST" and file_full_path:
        action = request.POST.get('action')
        if action == "save":
            new_content = request.POST.get('content', '')
            try:
                with open(file_full_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                file_content = new_content
                request.session['workspace_msg'] = f"File {filepath} saved successfully."
            except Exception as e:
                request.session['workspace_msg'] = f"Failed to save: {str(e)}"
            return redirect(f"{request.path}?session_id={session_id or ''}&file={filepath}")

    # Build file tree
    files_tree = []
    for root, dirs, filenames in os.walk(workspace_path):
        for name in filenames:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, workspace_path)
            files_tree.append(rel)
            
    msg = request.session.pop('workspace_msg', None)
    
    context = {
        'files_tree': sorted(files_tree),
        'workspace_path': workspace_path,
        'session_id': session_id,
        'session': session_obj,
        'selected_file': filepath,
        'file_content': file_content,
        'message': msg
    }
    return render(request, 'core/workspace.html', context)
