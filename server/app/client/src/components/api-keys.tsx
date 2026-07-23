import { useEffect, useState } from "react"
import { Check, Copy, KeyRound, Plus, Trash2 } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { createKey, fetchKeys, revokeKey, type ApiKey, type CreatedKey } from "@/lib/api"

/** Create, list, and revoke the current user's API keys. */
export function ApiKeys() {
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [label, setLabel] = useState("")
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The plaintext key is returned once on creation; hold it until dismissed.
  const [newKey, setNewKey] = useState<CreatedKey | null>(null)

  useEffect(() => {
    fetchKeys()
      .then(setKeys)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  async function handleCreate() {
    setCreating(true)
    setError(null)
    try {
      const created = await createKey(label.trim())
      setNewKey(created)
      setLabel("")
      setKeys(await fetchKeys())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setCreating(false)
    }
  }

  async function handleRevoke(id: number) {
    setError(null)
    try {
      await revokeKey(id)
      setKeys(await fetchKeys())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div>
      <h2 className="flex items-center gap-2 font-heading text-lg font-medium">
        <KeyRound className="size-4" />
        API keys
      </h2>
      <p className="mb-3 text-sm text-muted-foreground">
        Use a key as the <code>API_KEY</code> when installing the plugin. The secret is shown
        only once — store it somewhere safe.
      </p>
      <div className="flex flex-col gap-4">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {newKey && <NewKeyBanner created={newKey} onDismiss={() => setNewKey(null)} />}

        <div className="flex gap-2">
          <Input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            placeholder="Label (e.g. laptop)"
            className="flex-1"
          />
          <Button onClick={handleCreate} disabled={creating}>
            <Plus />
            Create key
          </Button>
        </div>

        <ScrollArea className="w-full rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Label</TableHead>
              <TableHead>Prefix</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Last used</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {keys.map((key) => (
              <TableRow key={key.id}>
                <TableCell className="font-medium">{key.label || "—"}</TableCell>
                <TableCell className="font-mono text-muted-foreground">{key.prefix}…</TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(key.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {key.last_used_at ? new Date(key.last_used_at).toLocaleString() : "Never"}
                </TableCell>
                <TableCell>
                  <Badge variant={key.status === "active" ? "secondary" : "outline"}>
                    {key.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  {key.status === "active" && (
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleRevoke(key.id)}
                    >
                      <Trash2 />
                      Revoke
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {keys.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  No API keys yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        </ScrollArea>
      </div>
    </div>
  )
}

function NewKeyBanner({ created, onDismiss }: { created: CreatedKey; onDismiss: () => void }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    await navigator.clipboard.writeText(created.key)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-border bg-muted/40 p-3">
      <p className="text-sm font-medium">
        Key created{created.label ? ` for "${created.label}"` : ""}. Copy it now — it won't be
        shown again.
      </p>
      <div className="flex items-center gap-2">
        <code className="flex-1 overflow-x-auto rounded-xl bg-background px-3 py-2 font-mono text-sm">
          {created.key}
        </code>
        <Button variant="outline" size="sm" onClick={copy}>
          {copied ? <Check /> : <Copy />}
          {copied ? "Copied" : "Copy"}
        </Button>
        <Button variant="ghost" size="sm" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  )
}
