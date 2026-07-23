import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

// Radix Select forbids an empty-string item value, so "all" is a sentinel.
const ALL = "__all__"

/** Dropdown to narrow a view to one user (admins / account owners). */
export function UserFilter({
  users,
  value,
  onChange,
}: {
  users: string[]
  value: string
  onChange: (email: string) => void
}) {
  return (
    <Select value={value || ALL} onValueChange={(v) => onChange(v === ALL ? "" : v)}>
      <SelectTrigger className="w-56">
        <SelectValue placeholder="All users" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>All users</SelectItem>
        {users.map((u) => (
          <SelectItem key={u} value={u}>
            {u}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
