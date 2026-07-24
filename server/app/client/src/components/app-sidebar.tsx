import { Activity, Building2, KeyRound, LayoutDashboard, TableProperties } from "lucide-react"
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
import type { Me } from "@/lib/api"

const NAV = [
  { title: "Overview", to: "/", icon: LayoutDashboard },
  { title: "Sessions", to: "/sessions", icon: TableProperties },
  { title: "Accounts", to: "/accounts", icon: Building2, adminOnly: true },
  { title: "API keys", to: "/keys", icon: KeyRound },
]

/** Left-hand navigation between the dashboard screens. */
export function AppSidebar({ me }: { me: Me }) {
  const { pathname } = useLocation()
  const nav = NAV.filter((item) => !item.adminOnly || me.is_admin)

  return (
    <Sidebar>
      <SidebarHeader className="px-3 py-4">
        <div className="flex items-center gap-2">
          <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <Activity className="size-4" />
          </div>
          <span className="font-heading text-base font-semibold">Claude Usage</span>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {nav.map((item) => (
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
