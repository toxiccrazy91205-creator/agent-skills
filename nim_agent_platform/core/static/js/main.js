// Helper to get CSRF token from cookies
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Global agent controller state
const AgentController = {
    isRunning: false,
    autoPilot: false,
    sessionId: null,

    init(sessionId) {
        this.sessionId = sessionId;
        this.autoPilot = document.getElementById('autopilot-toggle')?.checked || false;
        
        // Bind UI events
        document.getElementById('autopilot-toggle')?.addEventListener('change', (e) => {
            this.autoPilot = e.target.checked;
            this.logTerminal(`System: Auto-pilot mode toggled ${this.autoPilot ? 'ON' : 'OFF'}`);
        });

        document.getElementById('step-btn')?.addEventListener('click', () => {
            this.startStep(false);
        });

        document.getElementById('run-btn')?.addEventListener('click', () => {
            this.startStep(false);
        });

        this.scrollChatBottom();
        this.scrollTerminalBottom();
        this.logTerminal("System: NVIDIA NIM Agent Console Initialized.");
    },

    scrollChatBottom() {
        const chatHistory = document.getElementById('chat-history');
        if (chatHistory) {
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }
    },

    scrollTerminalBottom() {
        const term = document.getElementById('terminal-panel');
        if (term) {
            term.scrollTop = term.scrollHeight;
        }
    },

    logTerminal(text, type = 'info') {
        const term = document.getElementById('terminal-panel');
        if (!term) return;

        const line = document.createElement('div');
        line.className = 'terminal-line';
        
        const promptSpan = document.createElement('span');
        promptSpan.className = 'terminal-prompt';
        promptSpan.textContent = 'nim-agent$ ';
        
        const outputSpan = document.createElement('span');
        outputSpan.className = 'terminal-output';
        outputSpan.textContent = text;
        
        if (type === 'error') {
            outputSpan.style.color = '#ef4444';
        } else if (type === 'success') {
            outputSpan.style.color = '#10b981';
        } else if (type === 'warning') {
            outputSpan.style.color = '#fbbf24';
        } else if (type === 'system') {
            outputSpan.style.color = '#a855f7';
        }

        line.appendChild(promptSpan);
        line.appendChild(outputSpan);
        term.appendChild(line);
        this.scrollTerminalBottom();
    },

    appendChatBubble(role, content, toolCalls = null) {
        const chatHistory = document.getElementById('chat-history');
        if (!chatHistory) return;

        const bubble = document.createElement('div');
        bubble.className = `chat-bubble chat-bubble-${role}`;

        const header = document.createElement('h4');
        header.textContent = role;
        bubble.appendChild(header);

        if (content) {
            const body = document.createElement('p');
            // Clean simple formatting of content (markdown is handled server-side initially, 
            // but for dynamically appended items, we do simple replacement or HTML)
            body.innerHTML = content.replace(/\n/g, '<br>');
            bubble.appendChild(body);
        }

        if (toolCalls && toolCalls.length > 0) {
            const toolsBox = document.createElement('div');
            toolsBox.className = 'tool-call-box';
            
            const boxTitle = document.createElement('h5');
            boxTitle.textContent = "Requested Tool Calls:";
            toolsBox.appendChild(boxTitle);

            toolCalls.forEach(tc => {
                const tcItem = document.createElement('div');
                tcItem.style.marginBottom = '8px';
                tcItem.style.fontSize = '0.85rem';
                tcItem.innerHTML = `<strong>Tool:</strong> <code>${tc.function.name}</code><br><strong>Args:</strong> <code>${tc.function.arguments}</code>`;
                toolsBox.appendChild(tcItem);
            });
            bubble.appendChild(toolsBox);
        }

        chatHistory.appendChild(bubble);
        this.scrollChatBottom();
    },

    setLoadingState(loading) {
        this.isRunning = loading;
        const stepBtn = document.getElementById('step-btn');
        const runBtn = document.getElementById('run-btn');
        const statusBadge = document.getElementById('session-status-badge');

        if (stepBtn) stepBtn.disabled = loading;
        if (runBtn) runBtn.disabled = loading;
        
        if (statusBadge) {
            if (loading) {
                statusBadge.textContent = "RUNNING";
                statusBadge.className = "badge badge-warning";
            } else {
                statusBadge.textContent = "IDLE";
                statusBadge.className = "badge badge-success";
            }
        }
    },

    async startStep(isApprovedToolCall = false) {
        if (this.isRunning) return;
        this.setLoadingState(true);
        this.logTerminal("Contacting NVIDIA NIM API...", 'system');

        try {
            const response = await fetch(`/sessions/${this.sessionId}/step/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ approved: isApprovedToolCall })
            });

            const data = await response.json();

            if (data.status === 'error') {
                this.logTerminal(`Error: ${data.message}`, 'error');
                alert(data.message);
                this.setLoadingState(false);
                return;
            }

            if (data.status === 'completed') {
                this.logTerminal("LLM response completed.", 'success');
                this.appendChatBubble('assistant', data.content);
                this.setLoadingState(false);
                return;
            }

            if (data.status === 'pending_approval') {
                this.logTerminal("Agent requested tool execution.", 'warning');
                this.appendChatBubble('assistant', data.content, data.tool_calls);
                
                // If autopilot, auto approve and run!
                if (this.autoPilot) {
                    this.logTerminal("Auto-pilot active. Executing tools in 1.5 seconds...", 'system');
                    this.setLoadingState(false);
                    setTimeout(() => {
                        this.startStep(true);
                    }, 1500);
                } else {
                    // Create manual approval UI
                    this.logTerminal("Waiting for manual approval to run tools.", 'warning');
                    this.setLoadingState(false);
                    this.showApprovalPrompt();
                }
                return;
            }

            if (data.status === 'tool_executed') {
                this.logTerminal("Tools executed successfully.", 'success');
                
                data.results.forEach(res => {
                    this.logTerminal(`Ran tool: ${res.name}`, 'system');
                    try {
                        const parsed = JSON.parse(res.result);
                        if (parsed.status === 'success') {
                            this.logTerminal(`Result: ${parsed.message || 'Success'}`, 'success');
                            if (parsed.output) {
                                this.logTerminal(`Command output:\n${parsed.output}`);
                            }
                        } else {
                            this.logTerminal(`Tool returned error: ${parsed.message}`, 'error');
                        }
                    } catch (e) {
                        this.logTerminal(`Result raw:\n${res.result}`);
                    }
                    // Append tool output to chat bubble
                    this.appendChatBubble('tool', res.result);
                });

                this.setLoadingState(false);

                // Auto pilot triggers the next turn automatically!
                if (this.autoPilot) {
                    this.logTerminal("Auto-pilot active. Contacting NIM for next turn in 1.5 seconds...", 'system');
                    setTimeout(() => {
                        this.startStep(false);
                    }, 1500);
                }
                return;
            }

        } catch (error) {
            this.logTerminal(`Network Error: ${error.message}`, 'error');
            this.setLoadingState(false);
        }
    },

    showApprovalPrompt() {
        const chatHistory = document.getElementById('chat-history');
        if (!chatHistory) return;

        const container = document.createElement('div');
        container.id = 'manual-approval-box';
        container.className = 'tool-call-box';
        container.style.borderColor = 'var(--color-primary)';
        container.style.background = 'rgba(0, 242, 254, 0.03)';
        container.style.marginTop = '16px';
        container.style.alignSelf = 'center';
        container.style.width = '100%';

        const text = document.createElement('p');
        text.innerHTML = `<strong>Manual Approval Required:</strong> The agent needs permission to write files or run commands.`;
        container.appendChild(text);

        const actions = document.createElement('div');
        actions.style.display = 'flex';
        actions.style.gap = '12px';
        actions.style.marginTop = '12px';

        const approveBtn = document.createElement('button');
        approveBtn.className = 'btn btn-primary';
        approveBtn.style.padding = '8px 16px';
        approveBtn.style.fontSize = '0.85rem';
        approveBtn.textContent = "Approve & Run Tools";
        approveBtn.onclick = () => {
            container.remove();
            this.startStep(true);
        };

        const rejectBtn = document.createElement('button');
        rejectBtn.className = 'btn btn-secondary';
        rejectBtn.style.padding = '8px 16px';
        rejectBtn.style.fontSize = '0.85rem';
        rejectBtn.textContent = "Deny";
        rejectBtn.onclick = () => {
            container.remove();
            this.logTerminal("Tool call denied by user.", 'error');
        };

        actions.appendChild(approveBtn);
        actions.appendChild(rejectBtn);
        container.appendChild(actions);
        chatHistory.appendChild(container);
        this.scrollChatBottom();
    }
};

window.AgentController = AgentController;
