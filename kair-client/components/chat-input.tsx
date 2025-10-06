'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Button } from "@/components/ui/button";
import { Send } from 'lucide-react';
import { config } from "@/config";
import ReactMarkdown from 'react-markdown';
import { useAuth } from '@/context/auth-context';
import { useSecureFetch } from '@/hooks/useSecureFetch';
import remarkGfm from 'remark-gfm';

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
}

export default function ChatInput({ addMessage, projectId, onRefreshRequest }: ChatInputProps) {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const { user } = useAuth();
  const secureFetch = useSecureFetch(); // Get the secure fetch function

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null); // Ref for the scrollable message container

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

  // Fetch chat history on component mount
  useEffect(() => {
    if (projectId) {
      const fetchHistory = async () => {
        try {
          console.log("Fetching chat history for project ID:", projectId);
            const response = await secureFetch(`${config.apiBaseUrl}/api/chat/history?project_id=${projectId}`);
          if (response.ok) {
            const data = await response.json();
            setMessages(data.history || []);
          }
        } catch (error) {
          console.error("Failed to fetch chat history:", error);
        }
      };
      fetchHistory();
    }
  }, [projectId]);


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
      // Expand prompt with user profile context
      const expandedPrompt = trimmedMessage;
      // if (user?.profile) {
      //     expandedPrompt =
      //         `User profile:\n` +
      //         `Biosketch: ${user.profile.biosketch}\n` +
      //         `Expertise: ${user.profile.expertise}\n` +
      //         `Projects: ${user.profile.projects}\n\n` +
      //         `User query: ${trimmedMessage}`;
      // }

      const response = await secureFetch(`${config.apiBaseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: expandedPrompt, project_id: projectId }),
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

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={
              msg.sender === 'user'
                ? "text-right"
                : "text-left"
            }
          >
            <div
              className={
                msg.sender === 'user'
                  ? "inline-block bg-blue-100 dark:bg-blue-900 rounded px-3 py-2"
                  : "inline-block bg-gray-100 dark:bg-gray-800 rounded px-3 py-2"
              }
            >
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
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
        className="p-4 bg-background border-t flex items-center gap-2"
      >
        <textarea
          ref={inputRef} // Attach the ref to the textarea element
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Send a message..."
          className="flex-grow resize-none border rounded px-3 py-2 max-h-40 overflow-y-auto"
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
        >
          <Send className="h-4 w-4" />
          <span className="sr-only">Send message</span>
        </Button>
      </form>
    </div>
  );
}