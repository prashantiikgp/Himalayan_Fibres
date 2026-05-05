/**
 * <ImportContactsDialog> — modal CSV/Excel uploader.
 */

import { useState, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { importContacts, type ImportResponse } from "@/api/contacts";
import { track } from "@/lib/analytics";

export function ImportContactsDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<ImportResponse | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: importContacts,
    onSuccess: (data) => {
      setResult(data);
      track("contact_imported", { count: data.imported });
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setResult(null);
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    mutation.mutate(file);
  }

  function handleClose(o: boolean) {
    setOpen(o);
    if (!o) {
      setResult(null);
      mutation.reset();
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <Upload className="mr-1 h-4 w-4" /> Import
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import Contacts</DialogTitle>
          <DialogDescription>
            CSV or Excel (.xlsx). Required column: <code>email</code>. Optional:{" "}
            <code>first_name</code>, <code>last_name</code>, <code>company</code>,{" "}
            <code>phone</code>, <code>country</code>. Duplicate emails are skipped.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="import-file" className="text-xs text-text-muted">
              File
            </Label>
            <input
              id="import-file"
              ref={fileInput}
              type="file"
              accept=".csv,.xlsx,.xls"
              required
              className="text-sm text-text file:mr-3 file:rounded-md file:border-0 file:bg-card file:px-3 file:py-1 file:text-text-muted hover:file:bg-card/70"
            />
          </div>

          {mutation.isError && (
            <p role="alert" className="text-sm text-danger">
              Import failed: {(mutation.error as Error).message}
            </p>
          )}

          {result && (
            <div className="rounded-md border border-border bg-card/40 p-3 text-sm">
              <p className="font-semibold text-success">
                Imported {result.imported}, skipped {result.skipped}.
              </p>
              {result.errors.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs text-text-muted">
                    {result.errors.length} row error(s)
                  </summary>
                  <ul className="mt-1 max-h-40 list-disc overflow-auto pl-5 text-xs text-text-muted">
                    {result.errors.slice(0, 50).map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}

          <DialogFooter className="mt-2">
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={mutation.isPending}>
                {result ? "Close" : "Cancel"}
              </Button>
            </DialogClose>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Uploading…" : "Import"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
