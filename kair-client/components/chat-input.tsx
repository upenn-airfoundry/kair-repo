'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Button } from "@/components/ui/button";
import { Send, Upload } from 'lucide-react';
import { config } from "@/config";
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import { useSecureFetch } from '@/hooks/useSecureFetch';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
// Optional (only if you expect raw HTML in the markdown):
// import rehypeRaw from 'rehype-raw';
// import rehypeSanitize from 'rehype-sanitize';

// Lightweight markdown component overrides to avoid horizontal overflow
const useMarkdownComponents = () => {
  return useMemo<Components>(() => ({
    // Keep pre/Code scrollable and avoid horizontal overflow
    pre: ({ className, ...props }: React.ComponentProps<'pre'>) => (
      <pre
        {...props}
        className={`overflow-x-auto max-w-full ${className ?? ''}`}
      />
    ),
    code: (
      { inline, className, children, ...props }: { inline?: boolean } & React.ComponentProps<'code'>
    ) =>
      inline ? (
        <code
          {...props}
          className={`break-words whitespace-normal ${className ?? ''}`}
        >
          {children}
        </code>
      ) : (
        <code {...props} className={className}>{children}</code>
      ),
    table: ({ children, ...rest }: React.ComponentProps<'table'>) => (
      <div className="overflow-x-auto max-w-full">
        <table {...rest}>{children}</table>
      </div>
    ),
    a: ({ className, ...props }: React.ComponentProps<'a'>) => (
      <a
        {...props}
        target="_blank"
        rel="noopener noreferrer"
        className={`break-words underline ${className ?? ''}`}
      />
    ),
    // Remove p/li overrides that force break-all/whitespace-pre-wrap.
  }), []);
};

// Normalize markdown so headings/line breaks render as intended
const normalizeMarkdown = (input: string): string => {
  if (!input) return '';
  let s = input.trim();
  // If content is wrapped in a fenced block, strip the outer fences
  if (s.startsWith('```')) {
    s = s.replace(/^```[a-zA-Z0-9_-]*\s*\n?/, '');
    s = s.replace(/\n?```\s*$/, '');
  }
  // If we see literal \n but no actual newlines, unescape
  if (s.includes('\\n') && !s.includes('\n')) {
    s = s.replace(/\\n/g, '\n');
  }
  // Dedent if most lines are indented (e.g., LLM returned a code-indented block)
  const lines = s.split('\n');
  let minIndent = Number.POSITIVE_INFINITY;
  let nonEmpty = 0;
  for (const ln of lines) {
    if (ln.trim().length === 0) continue;
    nonEmpty++;
    const m = ln.match(/^[\t ]*/)?.[0] ?? '';
    minIndent = Math.min(minIndent, m.length);
  }
  if (nonEmpty > 0 && minIndent >= 4) {
    s = lines.map(l => l.slice(minIndent)).join('\n');
  }
  return s;
};

// Message type
export interface Message {
  id: string;
  sender: 'user' | 'bot';
  content: string;
}

interface ChatInputProps {
  addMessage: (message: Message) => void;
  projectId: number;
  onRefreshRequest: () => void; // Add the new prop to the interface
  selectedTaskId?: number | null;
}

export default function ChatInput({ addMessage, projectId, onRefreshRequest, selectedTaskId }: ChatInputProps) {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const secureFetch = useSecureFetch(); // Get the secure fetch function
  const mdComponents = useMarkdownComponents();

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null); // Ref for the scrollable message container
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Function to scroll to the bottom of the message list
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // Scroll to bottom whenever new messages are added
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Effect to handle resizing and maintain scroll position from the bottom
  useEffect(() => {
    const scrollContainer = scrollContainerRef.current;
    if (!scrollContainer) return;

    let oldScrollHeight = 0;
    let oldScrollTop = 0;

    const observer = new ResizeObserver(() => {
      if (scrollContainer.scrollHeight !== oldScrollHeight) {
        scrollContainer.scrollTop = oldScrollTop + (scrollContainer.scrollHeight - oldScrollHeight);
      }
    });

    const handleScroll = () => {
      oldScrollHeight = scrollContainer.scrollHeight;
      oldScrollTop = scrollContainer.scrollTop;
    };

    // Observe the container and listen for scroll events to update our stored position
    observer.observe(scrollContainer);
    scrollContainer.addEventListener('scroll', handleScroll);

    // Cleanup
    return () => {
      observer.disconnect();
      scrollContainer.removeEventListener('scroll', handleScroll);
    };
  }, []);

  // Fetch chat history when project changes; clear old messages first
  useEffect(() => {
    if (!projectId) return;

    const fetchHistoryWithRetry = async () => {
      setMessages([]); // clear immediately on project change
      const maxAttempts = 6;
      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        try {
          const response = await secureFetch(`${config.apiBaseUrl}/api/chat/history?project_id=${projectId}`, {
            cache: 'no-store',
          });
          if (response.ok) {
            const data = await response.json();
            if (data.history && data.history.length > 0) {
              setMessages(data.history);
            } else {
              setMessages([{ id: 'welcome', sender: 'bot', content: 'How can the KAIR Assistant help you today?' }]);
            }
            return;
          }
        } catch {
          /* ignore and retry */
        }
        // backoff: 100ms, 200ms, ...
        await new Promise((r) => setTimeout(r, 100 * (attempt + 1)));
      }
      // Fallback if still failing
      setMessages([{ id: 'welcome', sender: 'bot', content: 'How can the KAIR Assistant help you today?' }]);
    };

    fetchHistoryWithRetry();
  }, [projectId, secureFetch]);


  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage) return;

    const userMessageId = Date.now().toString();
    const userMsg: Message = { id: userMessageId, sender: 'user', content: trimmedMessage };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    addMessage(userMsg);
    setMessage('');
    setIsLoading(true);

    try {
      const expandedPrompt = trimmedMessage;
      const payload: { prompt: string; project_id: number; selected_task_id?: number } = {
        prompt: expandedPrompt,
        project_id: projectId,
      };
      if (selectedTaskId != null) payload.selected_task_id = Number(selectedTaskId);
      const response = await secureFetch(`${config.apiBaseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        credentials: 'include',
      });

      if (!response.ok) throw new Error('Network response was not ok');
      const botResponse = await response.json();

      // Check for the refresh trigger in the response
      if (botResponse.data.refresh_project) {
        console.log("Refresh project requested by backend.");
        onRefreshRequest(); // Call the handler function from the parent
      }

      const botMessageId = Date.now().toString() + '-bot';
      const botMsg: Message = { id: botMessageId, sender: 'bot', content: botResponse.data.message };
      setMessages((prev) => [...prev, botMsg]);
      addMessage(botMsg);
    } catch (error) {
      const errorMsg: Message = {
        id: Date.now().toString() + '-error',
        sender: 'bot',
        content: 'Sorry, something went wrong. Please try again. ' + error,
      };
      setMessages((prev) => [...prev, errorMsg]);
      addMessage(errorMsg);
    } finally {
      setIsLoading(false);
      // Set focus back to the input field
      inputRef.current?.focus();
    }
  };

  const handleUploadClick = () => {
    if (selectedTaskId == null || isUploading) return;
    fileInputRef.current?.click();
  };

  const handleFileChange: React.ChangeEventHandler<HTMLInputElement> = async (e) => {
    const file = e.target.files?.[0];
    // Reset input so selecting the same file again still triggers change
    e.currentTarget.value = '';
    if (!file || selectedTaskId == null) return;
    try {
      setIsUploading(true);
      const text = await file.text();
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch (err) {
        const errorMsg: Message = {
          id: Date.now().toString() + '-error',
          sender: 'bot',
          content: `Failed to parse JSON file: ${(err as Error)?.message || err}`,
        };
        setMessages((prev) => [...prev, errorMsg]);
        addMessage(errorMsg);
        return;
      }
      // POST to backend to attach JSON to the selected task
      const resp = await secureFetch(`${config.apiBaseUrl}/api/task/${Number(selectedTaskId)}/entities`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ json: parsed, filename: file.name }),
      });
      if (!resp.ok) {
        const errorText = await resp.text().catch(() => '');
        throw new Error(errorText || 'Upload failed');
      }
      // Notify user and optionally trigger UI refreshes
      const botMsg: Message = {
        id: Date.now().toString() + '-bot',
        sender: 'bot',
        content: `Uploaded JSON from "${file.name}" and linked it to task ${selectedTaskId}.`,
      };
      setMessages((prev) => [...prev, botMsg]);
      addMessage(botMsg);
      // Dispatch a custom event so any details viewer can refetch entities if listening
      window.dispatchEvent(new CustomEvent('task-entities-updated', { detail: { taskId: Number(selectedTaskId) } }));
    } catch (err) {
      const errorMsg: Message = {
        id: Date.now().toString() + '-error',
        sender: 'bot',
        content: `Upload error: ${(err as Error)?.message || err}`,
      };
      setMessages((prev) => [...prev, errorMsg]);
      addMessage(errorMsg);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="flex flex-col h-full w-full max-w-full min-w-0 overflow-x-hidden">
      {/* Message list */}
      <div
        ref={scrollContainerRef}
        className="flex-1 w-full max-w-full min-w-0 overflow-y-auto overflow-x-auto p-4 space-y-4"
      >
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={
              msg.sender === 'user'
                ? "text-right"
                : "text-left"
            }
            // Ensure message rows don't expand horizontally
            style={{ minWidth: 0, maxWidth: '100%' }}
          >
            <div
              className={
                msg.sender === 'user'
                  ? "inline-block bg-blue-100 dark:bg-blue-900 rounded px-3 py-2"
                  : "inline-block bg-gray-100 dark:bg-gray-800 rounded px-3 py-2"
              }
            >
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkBreaks]}
                  // If you expect raw HTML from the LLM, uncomment rehype plugins:
                  // rehypePlugins={[rehypeRaw, rehypeSanitize]}
                  components={mdComponents}
                >
                  {normalizeMarkdown(msg.content)}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="text-left">
            <div className="inline-flex items-center gap-2 bg-gray-100 dark:bg-gray-800 rounded px-3 py-2">
              <span className="inline-block h-3 w-3 rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground animate-spin" />
              <span className="text-sm text-muted-foreground">KAIR is thinking...</span>
            </div>
          </div>
        )}
        {/* Empty div to act as a scroll target */}
        <div ref={messagesEndRef} />
      </div>
      {/* Input form */}
      <form
        onSubmit={handleSubmit}
        className="p-4 bg-background border-t flex items-center gap-2 w-full max-w-full min-w-0 overflow-x-hidden"
      >
        <textarea
          ref={inputRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Make a request of the KAIR Assistant..."
          className="flex-1 w-0 min-w-0 max-w-full resize-none border rounded px-3 py-2 max-h-40 overflow-y-auto overflow-x-hidden"
          rows={1}
          disabled={isLoading}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !isLoading) {
              e.preventDefault();
              if (message.trim()) {
                handleSubmit(e);
              }
            }
          }}
        />
        <Button
          type="submit"
          size="icon"
          variant="ghost"
          disabled={!message.trim() || isLoading}
          aria-label="Send message"
          className="shrink-0"
        >
          <Send className="h-4 w-4" />
          <span className="sr-only">Send message</span>
        </Button>
        {/* JSON upload button appears only when a task is selected */}
        {selectedTaskId != null && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/json,.json"
              hidden
              onChange={handleFileChange}
            />
            <Button
              type="button"
              size="icon"
              variant="ghost"
              disabled={isUploading}
              onClick={handleUploadClick}
              aria-label="Upload JSON to selected task"
              title="Upload JSON to selected task"
              className="shrink-0"
            >
              {isUploading ? (
                <span className="inline-block h-4 w-4 rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
            </Button>
          </>
        )}
      </form>
    </div>
  );
}