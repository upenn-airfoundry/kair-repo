"use client"

import * as React from "react"
import { IconCirclePlusFilled, IconMail, type Icon } from "@tabler/icons-react"

import Link from "next/link"
import { usePathname } from "next/navigation"

import { Button } from "@/components/ui/button"
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@/components/ui/drawer"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"



export function NavMain({
  items,
  selectedTab,
  onTabSelect,
}: {
  items: {
    title: string
    url: string
    icon?: Icon
  }[],
  selectedTab: string,
  onTabSelect: (url: string) => void,
}) {
// Inside NavMain component
  const [importTab, setImportTab] = React.useState("pdfs");
  // const [selectedTab, setSelectedTab] = React.useState("pdfs")
  // State for PDF/Parquet
  const [pdfFiles, setPdfFiles] = React.useState<FileList | null>(null)
  const [parquetFiles, setParquetFiles] = React.useState<FileList | null>(null)
  // State for Database
  const [dbLink, setDbLink] = React.useState("")
  const [dbPort, setDbPort] = React.useState("")
  const [dbUser, setDbUser] = React.useState("")
  const [dbPassword, setDbPassword] = React.useState("")
  // Error state
  const [error, setError] = React.useState("")

  // Validation logic
  const isPdfValid = !!(pdfFiles && pdfFiles.length > 0)
  const isParquetValid = !!(parquetFiles && parquetFiles.length > 0)
  const isDbValid = Boolean(dbLink && dbPort && dbUser && dbPassword)

  function handleImport(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    if (importTab === "pdfs" && !isPdfValid) {
      setError("Please select at least one PDF file.")
      return
    }
    if (importTab === "database" && !isDbValid) {
      setError("Please fill in all database fields.")
      return
    }
    if (importTab === "parquet" && !isParquetValid) {
      setError("Please select at least one Parquet file.")
      return
    }
    setError("")
    // ...
  }

  // Helper for button style
  function getButtonClass(valid: boolean) {
    return valid ? "w-full" : "w-full opacity-50 cursor-not-allowed"
  }

  return (
    <SidebarGroup>
      <SidebarGroupContent className="flex flex-col gap-2">
        <SidebarMenu>
          <SidebarMenuItem className="flex items-center gap-2">
            <Drawer direction="right">
              <DrawerTrigger asChild>
                <SidebarMenuButton
                  tooltip="Import"
                  className="min-w-8 duration-200 ease-linear"
                >
                  <IconCirclePlusFilled />
                  <span>Import</span>
                </SidebarMenuButton>
              </DrawerTrigger>
              <DrawerContent>
                <DrawerHeader>
                  <DrawerTitle>Import Wizard</DrawerTitle>
                  <DrawerDescription>
                    Select the type of data source to import.
                  </DrawerDescription>
                </DrawerHeader>
                <div className="p-4">
                  <Tabs value={importTab} onValueChange={v => { setImportTab(v); setError("") }} className="w-full">
                    <TabsList className="grid w-full grid-cols-3">
                      <TabsTrigger value="pdfs">PDFs</TabsTrigger>
                      <TabsTrigger value="database">Database</TabsTrigger>
                      <TabsTrigger value="parquet">Parquet</TabsTrigger>
                    </TabsList>
                    <TabsContent value="pdfs" className="mt-4">
                      <form onSubmit={handleImport} className="grid gap-4">
                        <div className="grid w-full max-w-sm items-center gap-1.5">
                          <Label htmlFor="pdf-file">Select PDF File(s)</Label>
                          <Input id="pdf-file" type="file" multiple accept=".pdf" onChange={e => setPdfFiles(e.target.files)} />
                        </div>
                        <Button type="submit" className={getButtonClass(isPdfValid)}>
                          Import
                        </Button>
                        {error && <div className="text-destructive text-sm mt-1">{error}</div>}
                      </form>
                    </TabsContent>
                    <TabsContent value="database" className="mt-4">
                      <form onSubmit={handleImport} className="grid gap-4">
                        <div className="grid w-full items-center gap-1.5">
                          <Label htmlFor="db-link">Link</Label>
                          <Input id="db-link" type="text" placeholder="e.g., postgresql://host:port/db" value={dbLink} onChange={e => setDbLink(e.target.value)} />
                        </div>
                        <div className="grid w-full items-center gap-1.5">
                          <Label htmlFor="db-port">Port</Label>
                          <Input id="db-port" type="number" placeholder="e.g., 5432" value={dbPort} onChange={e => setDbPort(e.target.value)} />
                        </div>
                        <div className="grid w-full items-center gap-1.5">
                          <Label htmlFor="db-user">Username</Label>
                          <Input id="db-user" type="text" placeholder="Username" value={dbUser} onChange={e => setDbUser(e.target.value)} />
                        </div>
                        <div className="grid w-full items-center gap-1.5">
                          <Label htmlFor="db-password">Password</Label>
                          <Input id="db-password" type="password" placeholder="Password" value={dbPassword} onChange={e => setDbPassword(e.target.value)} />
                        </div>
                        <Button type="submit" className={getButtonClass(isDbValid)}>
                          Import
                        </Button>
                        {error && <div className="text-destructive text-sm mt-1">{error}</div>}
                      </form>
                    </TabsContent>
                    <TabsContent value="parquet" className="mt-4">
                      <form onSubmit={handleImport} className="grid gap-4">
                        <div className="grid w-full max-w-sm items-center gap-1.5">
                          <Label htmlFor="parquet-file">Select Parquet File(s)</Label>
                          <Input id="parquet-file" type="file" multiple accept=".parquet" onChange={e => setParquetFiles(e.target.files)} />
                        </div>
                        <Button type="submit" className={getButtonClass(isParquetValid)}>
                          Import
                        </Button>
                        {error && <div className="text-destructive text-sm mt-1">{error}</div>}
                      </form>
                    </TabsContent>
                  </Tabs>
                </div>
                <DrawerFooter>
                  <DrawerClose asChild>
                    <Button variant="outline">Close</Button>
                  </DrawerClose>
                </DrawerFooter>
              </DrawerContent>
            </Drawer>
          </SidebarMenuItem>
        </SidebarMenu>
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton
                asChild
                tooltip={item.title}
                className={
                  selectedTab === item.url
                    ? "bg-primary text-primary-foreground font-bold"
                    : ""
                }
                onClick={() => onTabSelect(item.url)}
              >
                <Link href={item.url}>
                  {item.icon && <item.icon />}
                  <span>{item.title}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
