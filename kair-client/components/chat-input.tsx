'use client';

import React, { useState } from 'react';
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Send } from 'lucide-react';

// Added interface for props
interface ChatInputProps {
  addMessage: (message: { id: string; sender: 'user' | 'bot'; content: string }) => void;
}

// Modified component signature to accept props
export default function ChatInput({ addMessage }: ChatInputProps) {
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false); // Added loading state

  const handleSubmit = async (e: React.FormEvent) => { // Made async
    e.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage) return;

    // Add user message optimistically
    const userMessageId = Date.now().toString();
    addMessage({ id: userMessageId, sender: 'user', content: trimmedMessage });
    setMessage(''); // Clear input after user message is added
    setIsLoading(true);

    try {
      // Send message to the backend API
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: trimmedMessage }),
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const botResponse = await response.json();

      // Add bot response
      const botMessageId = Date.now().toString() + '-bot'; // Ensure unique ID
      addMessage({ id: botMessageId, sender: 'bot', content: botResponse.content });

    } catch (error) {
      console.error('Error sending message:', error);
      // Optionally add an error message to the chat
      addMessage({
        id: Date.now().toString() + '-error',
        sender: 'bot',
        content: 'Sorry, something went wrong. Please try again.',
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="p-4 bg-background border-t flex items-center gap-2"
    >
      <Textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Send a message..."
        className="flex-grow resize-none"
        rows={1}
        disabled={isLoading} // Disable textarea when loading
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !isLoading) { // Prevent send while loading
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
        disabled={!message.trim() || isLoading} // Disable button when loading or empty
        aria-label="Send message"
      >
        <Send className="h-4 w-4" />
        <span className="sr-only">Send message</span>
      </Button>
    </form>
  );
} 