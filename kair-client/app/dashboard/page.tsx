"use client"

import { AppSidebar } from "@/components/app-sidebar"
import { ChartAreaInteractive } from "@/components/chart-area-interactive"
import { DataTable } from "@/components/data-table"
import { SectionCards } from "@/components/section-cards"
import { SiteHeader } from "@/components/site-header"
import {
  SidebarInset,
  SidebarProvider,
} from "@/components/ui/sidebar"
import { ProtectedRoute } from "@/components/protected-route"
import { useEffect, useState } from "react"
import { z } from "zod"

const dashboardSchema = z.object({
  id: z.number(),
  header: z.string(),
  type: z.string(),
  status: z.string(),
  target: z.string(),
  limit: z.string(),
  reviewer: z.string(),
})
type DashboardItem = z.infer<typeof dashboardSchema>

export default function Page() {
  const [data, setData] = useState<DashboardItem[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    async function fetchData() {
      try {
        const res = await fetch("/api/dashboard")
        if (!res.ok) throw new Error("Failed to fetch dashboard data")
        const json = await res.json()
        const parsed = z.array(dashboardSchema).safeParse(json)
        if (!parsed.success) throw new Error("Invalid data format")
        setData(parsed.data)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error")
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  if (!mounted) return null

  return (
    <ProtectedRoute>
      <SidebarProvider
        style={
          {
            "--sidebar-width": "calc(var(--spacing) * 72)",
            "--header-height": "calc(var(--spacing) * 12)",
          } as React.CSSProperties
        }
      >
        <AppSidebar variant="inset" />
        <SidebarInset>
          <SiteHeader />
          <div className="flex flex-1 flex-col">
            <div className="@container/main flex flex-1 flex-col gap-2">
              <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
                <SectionCards />
                <div className="px-4 lg:px-6">
                  <ChartAreaInteractive />
                </div>
                {loading ? (
                  <div className="text-center py-8">Loading...</div>
                ) : error ? (
                  <div className="text-center py-8 text-red-500">Error loading data: {error}</div>
                ) : Array.isArray(data) ? (
                  <DataTable data={data} />
                ) : null}
              </div>
            </div>
          </div>
        </SidebarInset>
      </SidebarProvider>
    </ProtectedRoute>
  )
}
