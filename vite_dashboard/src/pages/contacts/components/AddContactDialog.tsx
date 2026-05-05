/**
 * <AddContactDialog> — modal form for creating a contact.
 *
 * Required: first_name, phone. Optional: last_name, email, company, country.
 * On success: closes the dialog and invalidates the contacts list query so
 * the new row appears.
 */

import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createContact, type ContactCreate } from "@/api/contacts";
import { ApiError } from "@/lib/queryClient";
import { track } from "@/lib/analytics";
import { STRINGS } from "@/lib/strings";

const INITIAL: ContactCreate = {
  first_name: "",
  last_name: "",
  phone: "",
  email: "",
  company: "",
  country: "India",
};

export function AddContactDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<ContactCreate>(INITIAL);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: createContact,
    onSuccess: () => {
      track("contact_added", { source: "manual" });
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
      setForm(INITIAL);
      setError(null);
      setOpen(false);
    },
    onError: (err) => {
      setError(
        err instanceof ApiError && err.status === 409
          ? STRINGS.contacts.addDialog.duplicateEmail
          : err instanceof Error
            ? err.message
            : STRINGS.contacts.addDialog.genericError,
      );
    },
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!form.first_name.trim() || !form.phone.trim()) {
      setError(STRINGS.contacts.addDialog.validationRequired);
      return;
    }
    mutation.mutate(form);
  }

  const t = STRINGS.contacts.addDialog;

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setError(null); }}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="mr-1 h-4 w-4" /> {STRINGS.contacts.addButton}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t.title}</DialogTitle>
          <DialogDescription>
            {(() => {
              const [before, after] = t.description.split("{pending}");
              return (
                <>
                  {before}
                  <code>pending</code>
                  {after}
                </>
              );
            })()}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-3">
          <Field label={t.firstName} id="first_name" required value={form.first_name}
            onChange={(v) => setForm({ ...form, first_name: v })} />
          <Field label={t.lastName} id="last_name" value={form.last_name ?? ""}
            onChange={(v) => setForm({ ...form, last_name: v })} />
          <Field label={t.phone} id="phone" required value={form.phone} placeholder={t.phonePlaceholder}
            onChange={(v) => setForm({ ...form, phone: v })} />
          <Field label={t.email} id="email" type="email" value={form.email ?? ""}
            onChange={(v) => setForm({ ...form, email: v })} />
          <Field label={t.company} id="company" className="col-span-2" value={form.company ?? ""}
            onChange={(v) => setForm({ ...form, company: v })} />
          <Field label={t.country} id="country" className="col-span-2" value={form.country ?? ""}
            onChange={(v) => setForm({ ...form, country: v })} />

          {error && (
            <p role="alert" className="col-span-2 text-sm text-danger">
              {error}
            </p>
          )}

          <DialogFooter className="col-span-2 mt-2">
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={mutation.isPending}>
                {t.cancel}
              </Button>
            </DialogClose>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? t.saving : t.submit}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  id,
  value,
  onChange,
  required = false,
  type = "text",
  placeholder,
  className = "",
}: {
  label: string;
  id: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  type?: string;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <Label htmlFor={id} className="text-xs text-text-muted">
        {label}
      </Label>
      <Input
        id={id}
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
