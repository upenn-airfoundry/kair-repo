'use client';

import React, { useState } from 'react';
import { Button } from "@/components/ui/button";
import { Send } from 'lucide-react';
import { config } from "@/config";
import ReactMarkdown from 'react-markdown';

// Message type
interface Message {
  id: string;
  sender: 'user' | 'bot';
  content: string;
}

// No longer need addMessage prop, manage messages locally
export default function ChatInput() {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage) return;

    // Add user message
    const userMessageId = Date.now().toString();
    const userMsg: Message = { id: userMessageId, sender: 'user', content: trimmedMessage };
    setMessages((prev) => [...prev, userMsg]);
    setMessage('');
    setIsLoading(true);

    try {
      const response = await fetch(`${config.apiBaseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: trimmedMessage }),
      });

      if (!response.ok) throw new Error('Network response was not ok');
      const botResponse = await response.json();

      // Add bot response
      const botMessageId = Date.now().toString() + '-bot';
      setMessages((prev) => [
        ...prev,
        { id: botMessageId, sender: 'bot', content: botResponse.data.message }
      ]);
    } catch (error) {
      console.error("Error in handleSubmit:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString() + '-error',
          sender: 'bot',
          content: 'Sorry, something went wrong. Please try again.',
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
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
              <ReactMarkdown>{msg.content}</ReactMarkdown>
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
      </div>
      {/* Input form */}
      <form
        onSubmit={handleSubmit}
        className="p-4 bg-background border-t flex items-center gap-2"
      >
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Send a message..."
          className="flex-grow resize-none border rounded px-3 py-2"
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