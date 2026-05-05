/**
 * <ContactDrawer> — slide-in panel showing full contact detail.
 *
 * Tabs:
 *   • Profile  — view/edit name, phone, email, company, country, lifecycle, consent
 *   • Tags     — view/edit tags (comma-separated) + matched-segments (read-only)
 *   • Notes    — append a new note + view threaded notes
 *   • Activity — interaction timeline (read-only)
 *
 * Bug fixes by construction:
 *   B7 — no JS bridge for the row-edit button; click → onEdit handler →
 *        drawer opens via Radix Dialog state.
 *   B8 — Radix handles the mount race v1 worked around with hf-modal-closed
 *        CSS class toggling.
 */

import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ChannelBadge } from "@/components/badges/ChannelBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  addContactNote,
  setContactLifecycle,
  updateContact,
  useContactDetail,
  type ContactDetail,
  type ContactRow,
  type ContactUpdate,
  type LifecycleValue,
} from "@/api/contacts";
import { formatRelative } from "@/lib/format";
import { track } from "@/lib/analytics";
import { STRINGS } from "@/lib/strings";

const LIFECYCLE_OPTIONS = ["new_lead", "contacted", "interested", "customer", "churned"];
const CONSENT_OPTIONS = ["pending", "opted_in", "opted_out"];

export function ContactDrawer({
  contact,
  open,
  onOpenChange,
}: {
  contact: ContactRow | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const { data: detail, isLoading, error } = useContactDetail(contact ? contact.id : null);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md md:max-w-lg">
        <SheetHeader>
          <SheetTitle>
            {contact ? `${contact.first_name} ${contact.last_name}`.trim() || contact.id : STRINGS.contacts.drawer.fallbackTitle}
          </SheetTitle>
          <SheetDescription>
            {contact?.company || ""}
            {contact && contact.channels.length > 0 && (
              <span className="ml-2 inline-flex gap-1 align-middle">
                {contact.channels.map((ch) => (
                  <ChannelBadge key={ch} channel={ch} />
                ))}
              </span>
            )}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-auto px-card pb-card">
          {isLoading && <p className="py-6 text-sm text-text-muted">{STRINGS.contacts.drawer.loadingDetail}</p>}
          {error && (
            <p className="py-6 text-sm text-danger" role="alert">
              {STRINGS.contacts.drawer.loadFailedPrefix}{error.message}
            </p>
          )}
          {detail && contact && (
            <Tabs defaultValue="profile">
              <LifecycleQuickActions
                contactId={contact.id}
                currentLifecycle={detail.lifecycle}
                onUpdated={() => {
                  queryClient.invalidateQueries({ queryKey: ["contacts"] });
                  queryClient.invalidateQueries({
                    queryKey: ["contacts", "detail", contact.id],
                  });
                }}
              />
              <TabsList className="w-full justify-start">
                <TabsTrigger value="profile">{STRINGS.contacts.drawer.tabProfile}</TabsTrigger>
                <TabsTrigger value="tags">{STRINGS.contacts.drawer.tabTags}</TabsTrigger>
                <TabsTrigger value="notes">
                  {STRINGS.contacts.drawer.tabNotes} {detail.threaded_notes.length > 0 && `(${detail.threaded_notes.length})`}
                </TabsTrigger>
                <TabsTrigger value="activity">{STRINGS.contacts.drawer.tabActivity}</TabsTrigger>
              </TabsList>

              <TabsContent value="profile">
                <ProfileForm
                  detail={detail}
                  onSaved={() => {
                    queryClient.invalidateQueries({ queryKey: ["contacts"] });
                    queryClient.invalidateQueries({
                      queryKey: ["contacts", "detail", contact.id],
                    });
                  }}
                />
              </TabsContent>

              <TabsContent value="tags">
                <TagsForm
                  detail={detail}
                  onSaved={() => {
                    queryClient.invalidateQueries({ queryKey: ["contacts"] });
                    queryClient.invalidateQueries({
                      queryKey: ["contacts", "detail", contact.id],
                    });
                  }}
                />
              </TabsContent>

              <TabsContent value="notes">
                <NotesPanel
                  detail={detail}
                  onAdded={() => {
                    queryClient.invalidateQueries({
                      queryKey: ["contacts", "detail", contact.id],
                    });
                  }}
                />
              </TabsContent>

              <TabsContent value="activity">
                {detail.activity.length === 0 ? (
                  <p className="text-xs text-text-muted">{STRINGS.contacts.drawer.activityEmpty}</p>
                ) : (
                  <ul className="flex flex-col gap-1">
                    {detail.activity.map((a) => (
                      <li
                        key={a.id}
                        className="flex items-start gap-3 border-b border-border/40 py-2 text-xs last:border-0"
                      >
                        <span className="min-w-[120px] text-text-muted">
                          {formatRelative(a.created_at)}
                        </span>
                        <span className="font-mono text-[10px] uppercase text-text-muted">
                          {a.kind}
                        </span>
                        <span className="flex-1 text-text">{a.summary}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </TabsContent>
            </Tabs>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

/**
 * Quick-action lifecycle buttons. One click moves the contact through
 * the lifecycle (new_lead → contacted → interested → customer | churned)
 * and writes a `lifecycle_<value>` interaction so the Activity tab and
 * the "Needs follow-up" filter immediately reflect it.
 *
 * Mapped buttons (from BACKLOG_lifecycle_workflow.md):
 *   ✉️ Replied         → contacted
 *   ⭐ Interested       → interested
 *   ✅ Converted        → customer
 *   ❌ Not interested   → churned
 */
function LifecycleQuickActions({
  contactId,
  currentLifecycle,
  onUpdated,
}: {
  contactId: string;
  currentLifecycle: string;
  onUpdated: () => void;
}) {
  const t = STRINGS.contacts.drawer.lifecycleActions;
  const [pending, setPending] = useState<LifecycleValue | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ACTIONS: { value: LifecycleValue; label: string; icon: string }[] = [
    { value: "contacted", label: t.replied, icon: t.icons.replied },
    { value: "interested", label: t.interested, icon: t.icons.interested },
    { value: "customer", label: t.converted, icon: t.icons.converted },
    { value: "churned", label: t.notInterested, icon: t.icons.notInterested },
  ];

  async function handleClick(value: LifecycleValue) {
    setPending(value);
    setError(null);
    try {
      await setContactLifecycle(contactId, value);
      track("contact_lifecycle_quick_action", { from: currentLifecycle, to: value });
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="mb-3 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-xs text-text-muted">{t.label}:</span>
        <div className="flex flex-wrap gap-1.5">
          {ACTIONS.map((a) => (
            <Button
              key={a.value}
              type="button"
              size="sm"
              variant={currentLifecycle === a.value ? "default" : "outline"}
              disabled={pending !== null}
              onClick={() => handleClick(a.value)}
              className="h-7 px-2 text-xs"
            >
              <span className="mr-1">{a.icon}</span>
              {pending === a.value ? `${t.savingPrefix}${a.label}…` : a.label}
            </Button>
          ))}
        </div>
      </div>
      {error && (
        <p className="text-xs text-danger" role="alert">
          {t.failedPrefix}{error}
        </p>
      )}
    </div>
  );
}


function ProfileForm({ detail, onSaved }: { detail: ContactDetail; onSaved: () => void }) {
  const [form, setForm] = useState<ContactUpdate>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm({});
    setError(null);
  }, [detail.id]);

  const mutation = useMutation({
    mutationFn: (body: ContactUpdate) => updateContact(detail.id, body),
    onSuccess: () => {
      track("contact_edited", { fields_changed: Object.keys(form) });
      setForm({});
      setError(null);
      onSaved();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : STRINGS.contacts.drawer.saveFailed);
    },
  });

  function effective<K extends keyof ContactUpdate>(key: K, fallback: string): string {
    const v = form[key];
    return typeof v === "string" ? v : fallback;
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (Object.keys(form).length === 0) return;
    mutation.mutate(form);
  }

  const labels = STRINGS.contacts.drawer.profileFields;
  const t = STRINGS.contacts.drawer;

  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-3 pt-2">
      <FieldInput label={labels.firstName} id="first_name" value={effective("first_name", detail.first_name)}
        onChange={(v) => setForm({ ...form, first_name: v })} />
      <FieldInput label={labels.lastName} id="last_name" value={effective("last_name", detail.last_name)}
        onChange={(v) => setForm({ ...form, last_name: v })} />
      <FieldInput label={labels.phone} id="phone" value={effective("phone", detail.phone)}
        onChange={(v) => setForm({ ...form, phone: v })} />
      <FieldInput label={labels.email} id="email" type="email" value={effective("email", detail.email)}
        onChange={(v) => setForm({ ...form, email: v })} />
      <FieldInput label={labels.company} id="company" className="col-span-2"
        value={effective("company", detail.company)}
        onChange={(v) => setForm({ ...form, company: v })} />
      <FieldInput label={labels.country} id="country" value={effective("country", detail.country)}
        onChange={(v) => setForm({ ...form, country: v })} />
      <FieldSelect label={labels.lifecycle} id="lifecycle" options={LIFECYCLE_OPTIONS}
        value={effective("lifecycle", detail.lifecycle)}
        onChange={(v) => setForm({ ...form, lifecycle: v })} />
      <FieldSelect label={labels.consent} id="consent" options={CONSENT_OPTIONS}
        value={effective("consent_status", detail.consent_status)}
        onChange={(v) => setForm({ ...form, consent_status: v })} />
      <div className="col-span-1" />

      {error && (
        <p role="alert" className="col-span-2 text-sm text-danger">
          {error}
        </p>
      )}
      {mutation.isSuccess && (
        <p className="col-span-2 text-sm text-success">{t.saved}</p>
      )}

      <div className="col-span-2 flex justify-end gap-2 pt-2">
        <Button
          type="button"
          variant="outline"
          disabled={mutation.isPending || Object.keys(form).length === 0}
          onClick={() => { setForm({}); setError(null); }}
        >
          {t.reset}
        </Button>
        <Button type="submit" disabled={mutation.isPending || Object.keys(form).length === 0}>
          {mutation.isPending ? t.saving : t.saveChanges}
        </Button>
      </div>
    </form>
  );
}

function TagsForm({ detail, onSaved }: { detail: ContactDetail; onSaved: () => void }) {
  const [draft, setDraft] = useState(detail.tags.join(", "));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(detail.tags.join(", "));
    setError(null);
  }, [detail.id, detail.tags]);

  const mutation = useMutation({
    mutationFn: (tags: string[]) => updateContact(detail.id, { tags }),
    onSuccess: () => {
      track("contact_edited", { fields_changed: ["tags"] });
      onSaved();
    },
    onError: (err) => setError(err instanceof Error ? err.message : STRINGS.contacts.drawer.saveFailed),
  });

  const parsed = draft.split(",").map((t) => t.trim()).filter(Boolean);
  const dirty = JSON.stringify(parsed) !== JSON.stringify(detail.tags);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    mutation.mutate(parsed);
  }

  const t = STRINGS.contacts.drawer;

  return (
    <div className="flex flex-col gap-3 pt-2">
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <Label htmlFor="tags-input" className="text-xs text-text-muted">
          {t.tagsLabel}
        </Label>
        <Input
          id="tags-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t.tagsPlaceholder}
        />
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={!dirty || mutation.isPending}
            onClick={() => { setDraft(detail.tags.join(", ")); setError(null); }}
          >
            {t.reset}
          </Button>
          <Button type="submit" disabled={!dirty || mutation.isPending}>
            {mutation.isPending ? t.saving : t.saveTags}
          </Button>
        </div>
      </form>
      <Section title={t.matchedSegments}>
        {detail.matched_segments.length === 0 ? (
          <p className="text-xs text-text-muted">{t.noSegmentMatches}</p>
        ) : (
          <ul className="flex flex-wrap gap-1">
            {detail.matched_segments.map((s) => (
              <li
                key={s.id}
                className="rounded-pill border px-2 py-0.5 text-xs"
                style={{
                  borderColor: s.color ?? "var(--color-border)",
                  color: s.color ?? "var(--color-text-muted)",
                }}
              >
                {s.name}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

function NotesPanel({ detail, onAdded }: { detail: ContactDetail; onAdded: () => void }) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (body: string) => addContactNote(detail.id, body),
    onSuccess: () => {
      setDraft("");
      setError(null);
      onAdded();
    },
    onError: (err) => setError(err instanceof Error ? err.message : STRINGS.contacts.drawer.saveFailed),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    setError(null);
    mutation.mutate(draft);
  }

  const t = STRINGS.contacts.drawer;

  return (
    <div className="flex flex-col gap-3 pt-2">
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <Label htmlFor="note-input" className="text-xs text-text-muted">
          {t.addNote}
        </Label>
        <textarea
          id="note-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          placeholder={t.notePlaceholder}
          className="rounded-md border border-border bg-card p-2 text-sm text-text placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        />
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <div className="flex justify-end">
          <Button type="submit" size="sm" disabled={!draft.trim() || mutation.isPending}>
            {mutation.isPending ? t.saving : t.addNote}
          </Button>
        </div>
      </form>

      {detail.threaded_notes.length === 0 && !detail.legacy_notes && (
        <p className="text-xs text-text-muted">{t.noNotes}</p>
      )}
      {detail.threaded_notes.length > 0 && (
        <ul className="flex flex-col gap-2">
          {detail.threaded_notes.map((n) => (
            <li key={n.id} className="rounded-md border border-border bg-card/40 p-3 text-sm">
              <div className="flex items-center justify-between text-xs text-text-muted">
                <span>{n.author ?? "—"}</span>
                <span>{formatRelative(n.created_at)}</span>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-text">{n.body}</p>
            </li>
          ))}
        </ul>
      )}
      {detail.legacy_notes && (
        <Section title={t.legacyNotes}>
          <p className="whitespace-pre-wrap text-xs text-text-muted">{detail.legacy_notes}</p>
        </Section>
      )}
    </div>
  );
}

function FieldInput({
  label,
  id,
  value,
  onChange,
  type = "text",
  className = "",
}: {
  label: string;
  id: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <Label htmlFor={id} className="text-xs text-text-muted">
        {label}
      </Label>
      <Input id={id} type={type} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function FieldSelect({
  label,
  id,
  options,
  value,
  onChange,
  className = "",
}: {
  label: string;
  id: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <Label htmlFor={id} className="text-xs text-text-muted">
        {label}
      </Label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-md border border-border bg-card px-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">{title}</h3>
      {children}
    </div>
  );
}
