/**
 * Centralized UI strings (per STANDARDS §7 — i18n deferred, but every UI
 * string flows through here so a future i18n swap is mechanical).
 *
 * Convention: never hardcode user-facing text in JSX. Always import from here.
 */

export const STRINGS = {
  app: {
    name: "Himalayan Fibres Dashboard",
    tagline: "Internal ops surface for email + WhatsApp marketing",
  },
  auth: {
    loginTitle: "Sign in",
    passwordLabel: "Password",
    passwordPlaceholder: "Enter dashboard password",
    submit: "Sign in",
    error: "Incorrect password. Try again or contact your team admin.",
    expired: "Your session has expired. Please sign in again.",
  },
  nav: {
    skip: "Skip to content",
    sections: {
      whatsapp: "WhatsApp",
      email: "Email",
    },
  },
  home: {
    statusEmail: "Email",
    statusWhatsApp: "WhatsApp",
    statusOk: "Connected",
    statusMissing: "Not configured",
    kpiEmailsToday: "Emails Today",
    kpiWaToday: "WA Today",
    kpiContacts: "Contacts",
    kpiWindow: "24h Window",
    kpiOptedIn: "Opted In",
    kpiPending: "Pending",
    kpiWaReady: "WA Ready",
    kpiEmailCampaigns: "Email Campaigns",
    kpiWaCampaigns: "WA Campaigns",
    lifecycleTitle: "Lifecycle",
    activityTitle: "Recent Activity",
    activityEmpty: "No activity yet",
  },
  migrationCard: {
    titlePrefix: "This page lands in",
    body:
      "The {pageName} page is on the migration roadmap. Until it ships in v2, " +
      "use the v1 dashboard at the link below. All data writes from v1 are " +
      "visible to v2 (shared database).",
    openV1: "Open in v1 dashboard",
    sharedDb: "Both dashboards share the same database — no data migration needed.",
  },
  errors: {
    fatalConfig:
      "Dashboard failed to start: configuration validation error. " +
      "Check the YAML files in src/config/ against their Zod schemas in src/schemas/.",
    networkOffline: "You appear to be offline. Reconnect and refresh.",
    unknown: "Something went wrong. The error has been reported to our team.",
  },
  table: {
    empty: "No rows match your filters.",
    loading: "Loading…",
    pageOf: "Page {page} of {total}",
  },
  contacts: {
    addButton: "Add Contact",
    importButton: "Import",
    addDialog: {
      title: "Add Contact",
      description:
        "New contact lands with consent {pending}. WhatsApp ID is derived from the phone.",
      firstName: "First name *",
      lastName: "Last name",
      phone: "Phone *",
      phonePlaceholder: "10-digit mobile",
      email: "Email",
      company: "Company",
      country: "Country",
      validationRequired: "First name and phone are required.",
      duplicateEmail: "A contact with that email already exists.",
      genericError: "Failed to create contact",
      cancel: "Cancel",
      saving: "Saving…",
      submit: "Save Contact",
    },
    importDialog: {
      title: "Import Contacts",
      descriptionPrefix: "CSV or Excel (.xlsx). Required column: ",
      descriptionMiddle: ". Optional: ",
      descriptionSuffix: ". Duplicate emails are skipped.",
      fileLabel: "File",
      failedPrefix: "Import failed: ",
      result: "Imported {imported}, skipped {skipped}.",
      rowErrors: "{count} row error(s)",
      cancel: "Cancel",
      close: "Close",
      uploading: "Uploading…",
      submit: "Import",
    },
    drawer: {
      fallbackTitle: "Contact",
      loadingDetail: "Loading detail…",
      loadFailedPrefix: "Failed to load contact: ",
      tabProfile: "Profile",
      tabTags: "Tags",
      tabNotes: "Notes",
      tabActivity: "Activity",
      activityEmpty: "No recorded activity.",
      saveFailed: "Save failed",
      saved: "Saved.",
      reset: "Reset",
      saveChanges: "Save changes",
      saving: "Saving…",
      tagsLabel: "Tags (comma-separated)",
      tagsPlaceholder: "wool, premium, carpet",
      saveTags: "Save tags",
      matchedSegments: "Matched segments",
      noSegmentMatches: "Not matched to any active segment.",
      addNote: "Add note",
      notePlaceholder: "Append a timestamped note to this contact's thread…",
      noNotes: "No notes yet.",
      legacyNotes: "Legacy notes (read-only)",
      profileFields: {
        firstName: "First name",
        lastName: "Last name",
        phone: "Phone",
        email: "Email",
        company: "Company",
        country: "Country",
        lifecycle: "Lifecycle",
        consent: "Consent",
      },
      lifecycleActions: {
        label: "Mark as",
        replied: "Replied",
        interested: "Interested",
        converted: "Converted",
        notInterested: "Not interested",
        savingPrefix: "Saving ",
        failedPrefix: "Failed to update lifecycle: ",
      },
    },
  },
} as const;

/** Substitute `{key}` placeholders in a string. */
export function tFormat(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) =>
    key in vars ? String(vars[key]) : `{${key}}`,
  );
}
