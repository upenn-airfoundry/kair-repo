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


interface ChatInputProps {
  addMessage: (message: Message) => void;
}

export default function ChatInput({ addMessage }: ChatInputProps) {
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
    addMessage(userMsg); // Call the prop function to add message to parent
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
      const botMsg: Message = { id: botMessageId, sender: 'bot', content: botResponse.data.message };
      setMessages((prev) => [...prev, botMsg]);
      addMessage(botMsg); // Call the prop function to add message to parent
    } catch (error) {
       const errorMsg: Message = {
        id: Date.now().toString() + '-error',
        sender: 'bot',
        content: 'Sorry, something went wrong. Please try again. ' + error,
      };
      setMessages((prev) => [...prev, errorMsg]);
      addMessage(errorMsg); // Call the prop
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