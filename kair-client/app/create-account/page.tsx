import { Suspense } from "react"
import CreateAccount from "@/components/create-account"

export const dynamic = "force-dynamic";

export default function CreateAccountPage() {
  return (
    <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading…</div>}>
      <CreateAccount />
    </Suspense>
  )
}
