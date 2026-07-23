import { Activity, KeyRound, LayoutDashboard, TableProperties } from "lucide-react"
import { NavLink, useLocation } from "react-router"

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

const NAV = [
  { title: "Overview", to: "/", icon: LayoutDashboard },
  { title: "Sessions", to: "/sessions", icon: TableProperties },
  { title: "API keys", to: "/keys", icon: KeyRound },
]

/** Left-hand navigation between the dashboard screens. */
export function AppSidebar() {
  const { pathname } = useLocation()

  return (
    <Sidebar>
      <SidebarHeader className="px-3 py-4">
        <div className="flex items-center gap-2">
          <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Activity className="size-4" />
          </div>
          <span className="font-heading text-base font-semibold">Claude Usage</span>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton asChild isActive={pathname === item.to} tooltip={item.title}>
                    <NavLink to={item.to}>
                      <item.icon />
                      <span>{item.title}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  )
}
