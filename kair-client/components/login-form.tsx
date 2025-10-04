"use client";

import { useState } from "react";
import { useRouter } from 'next/navigation'; // Import useRouter
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { config } from "@/config";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/context/auth-context"; // Import the useAuth hook
import Link from "next/link";
import Image from 'next/image'

export function LoginForm({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const router = useRouter(); // Initialize useRouter

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${config.apiBaseUrl}/api/login`, {
        method: 'POST',
        credentials: 'include', // Include cookies in the request
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();

      if (response.ok && data.success) {
        login({
          name: data.user.name,
          email: email,
          organization: data.user.organization,
          avatar: data.user.avatar,
          profile: data.user.profile ?? null, // <-- include profile from server
          project_id: data.user.project_id // <-- include project_id from server
        });
        router.push('/chat'); // Redirect to /dashboard
      } else {
        setError(data.message || "Login failed. Please try again.");
      }
    } catch (err) {
      console.error("Login request failed:", err);
      setError("Unable to reach the KAIR backend server. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={cn("flex flex-col gap-6", className)} {...props}>
      <Card>
        <div className="flex justify-center items-center py-6 border-b">
          <Image
            src="/images/airfoundry-logo.png"
            width="234"
            height="65"
            alt="Airfoundry Logo"
          />
        </div>
        <CardHeader>
          <CardTitle>Login to your account</CardTitle>
          <CardDescription>
            Enter your email below to login to your account
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit}>
            <div className="flex flex-col gap-6">
              <div className="grid gap-3">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="m@example.com"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-3">
                <div className="flex items-center">
                  <Label htmlFor="password">Password</Label>
                  {/* <a
                    href="#"
                    className="ml-auto inline-block text-sm underline-offset-4 hover:underline"
                  >
                    Forgot your password?
                  </a> */}
                </div>
                <Input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                />
              </div>
              {error && (
                <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
              )}
              <div className="flex flex-col gap-3">
                <Button type="submit" className="w-full" disabled={isLoading}>
                  {isLoading ? "Logging in..." : "Login"}
                </Button>
                {/* <Button variant="outline" className="w-full" disabled={isLoading}>
                  Login with Google
                </Button> */}
                {/* Create Account Button */}
                <Link href="/create-account" passHref>
                  <Button variant="outline" className="w-full" type="button">
                    Create an account
                  </Button>
                </Link>
              </div>
            </div>
            {/* <div className="mt-4 text-center text-sm">
              Don&apos;t have an account?{" "}
              <a href="#" className="underline underline-offset-4">
                Sign up
              </a>
            </div> */}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
