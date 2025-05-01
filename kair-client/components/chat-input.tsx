'use client';

import React, { useState } from 'react';
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Send } from 'lucide-react';

export default function ChatInput() {
  const [message, setMessage] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Handle message submission logic here
    console.log('Submitted message:', message);
    setMessage(''); // Clear the input field after submission
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
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
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
        disabled={!message.trim()}
        aria-label="Send message"
      >
        <Send className="h-4 w-4" />
        <span className="sr-only">Send message</span>
      </Button>
    </form>
  );
} 