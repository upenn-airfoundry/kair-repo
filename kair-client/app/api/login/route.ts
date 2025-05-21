import { NextResponse } from 'next/server'

export async function POST(request: Request) {
  try {
    const { email, password } = await request.json()

    // --- Sample Credentials Check ---
    // Replace this with your actual database lookup and password hashing verification
    const SAMPLE_EMAIL = "test@example.com"
    const SAMPLE_PASSWORD = "password123" // In a real app, NEVER store plain text passwords

    if (email === SAMPLE_EMAIL && password === SAMPLE_PASSWORD) {
      // Successful login
      // In a real app, you would generate a session token (e.g., JWT)
      // and return it or set it in an HttpOnly cookie.
      return NextResponse.json({ success: true })
    } else {
      // Invalid credentials
      return NextResponse.json(
        { success: false, message: "Invalid email or password" },
        { status: 401 }
      )
    }
  } catch (error) {
    console.error("Login API error:", error)
    return NextResponse.json(
      { success: false, message: "Internal Server Error" },
      { status: 500 }
    )
  }
} 