import { NextRequest, NextResponse } from 'next/server';

// Function to introduce a delay
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const userMessage = body.message;

    // Simulate processing delay
    await delay(1000); // Wait for 1 second

    // Dummy response from the bot
    const botResponse = {
      content: `KAIR received: "${userMessage}". This is a dummy response.`,
    };

    return NextResponse.json(botResponse);
  } catch (error) {
    console.error("Error in /api/chat:", error);
    return NextResponse.json(
      { error: "Internal Server Error" },
      { status: 500 }
    );
  }
} 