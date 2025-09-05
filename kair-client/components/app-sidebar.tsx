"use client"

import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/context/auth-context";
import * as React from "react"
import {
  IconMessage,
  IconCamera,
  IconDashboard,
  IconDatabase,
  IconFileAi,
  IconFileDescription,
  IconFileWord,
  IconHelp,
  IconReport,
  IconSearch,
  IconSettings,
  IconBrain,
  IconAffiliate
} from "@tabler/icons-react"

import { NavMain } from "@/components/nav-main"
import { NavSecondary } from "@/components/nav-secondary"
import { NavUser } from "@/components/nav-user"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

const data = {
  user: {
    name: "kair-user",
    email: "kair-user@seas.upenn.edu",
    avatar: "/avatars/shadcn.jpg",
    organization: "KAIR",
  },
  navMain: [
    {
      title: "Dashboard",
      url: "/dashboard",
      icon: IconDashboard,
    },
    {
      title: "Chat",
      url: "/chat",
      icon: IconMessage,
    },
    // {
    //   title: "Retriever",
    //   url: "/retriever",
    //   icon: IconListDetails,
    // },
    // {
    //   title: "Crawler",
    //   url: "/crawler",
    //   icon: IconChartBar,
    // },
    // {
    //   title: "Data",
    //   url: "/data",
    //   icon: IconDatabase,
    // },
    {
      title: "Projects",
      url: "/projects",
      icon: IconAffiliate,
    },
    // {
    //   title: "Team",
    //   url: "/team",
    //   icon: IconUsers,
    // },
  ],
  navClouds: [
    {
      title: "Capture",
      icon: IconCamera,
      isActive: true,
      url: "#",
      items: [
        {
          title: "Active Proposals",
          url: "#",
        },
        {
          title: "Archived",
          url: "#",
        },
      ],
    },
    {
      title: "Proposal",
      icon: IconFileDescription,
      url: "#",
      items: [
        {
          title: "Active Proposals",
          url: "#",
        },
        {
          title: "Archived",
          url: "#",
        },
      ],
    },
    {
      title: "Prompts",
      icon: IconFileAi,
      url: "#",
      items: [
        {
          title: "Active Proposals",
          url: "#",
        },
        {
          title: "Archived",
          url: "#",
        },
      ],
    },
  ],
  navSecondary: [
    {
      title: "Settings",
      url: "#",
      icon: IconSettings,
    },
    {
      title: "Get Help",
      url: "mailto:zives@seas.upenn.edu",
      icon: IconHelp,
    },
    {
      title: "Search",
      url: "/retriever",
      icon: IconSearch,
    },
  ],
  documents: [
    {
      name: "Data Library",
      url: "#",
      icon: IconDatabase,
    },
    {
      name: "Reports",
      url: "#",
      icon: IconReport,
    },
    {
      name: "Word Assistant",
      url: "#",
      icon: IconFileWord,
    },
  ],
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { user } = useAuth();
  const pathname = usePathname();

  if (user) {
    data.user.email = user.email || data.user.email; // Use the user from context or fallback to default
    data.user.name = user.name || data.user.name; // Use the user from context or fallback to default
    data.user.avatar = user.avatar || data.user.avatar; // Use the user from context or fallback to default
    data.user.organization = user.organization || "KAIR"; // Use the user from context or fallback to default
}

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              className="data-[slot=sidebar-menu-button]:!p-1.5"
            >
              <a href="#">
                <IconBrain className="!size-5" />
                <span className="text-base font-semibold">KAIR Prototype</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain
          items={data.navMain}
          selectedTab={pathname}
          onTabSelect={() => {}}
        />
        <NavSecondary
          items={data.navSecondary}
          className="mt-auto"
        />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
    </Sidebar>
  )
}
