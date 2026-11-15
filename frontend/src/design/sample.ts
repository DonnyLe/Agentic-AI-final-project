// Real K-054 data and trace from a live run, used only by the design preview.
import type { GraphNode } from "@/components/Ascii.tsx";

export interface SampleSegment {
  id: string;
  speaker: string;
  text: string;
}

export interface SampleEvent {
  node: GraphNode;
  title: string;
  /** Tool calls and results, shown nested in mono. */
  steps?: string[];
}

export const SEGMENTS: SampleSegment[] = [
  {
    id: "S01",
    speaker: "Grace Liu",
    text: "Hi all, I'll be quick, the new login screen illustrations are in review, no blockers.",
  },
  { id: "S02", speaker: "Lena Okafor", text: "Thanks Grace. Aisha?" },
  {
    id: "S03",
    speaker: "Aisha Rahman",
    text: "So refresh is broken on staging. When the access token expires, the refresh call comes back 401 with 'invalid_signature', so people get bounced to login every fifteen minutes instead of silently refreshing.",
  },
  { id: "S04", speaker: "Dev Patel", text: "Since when?" },
  {
    id: "S05",
    speaker: "Aisha Rahman",
    text: "Since Thursday's deploy. And that deploy bumped jwt-verify-lite to 4.2.0, which, it's a brand new version, came out last week. So it's that. I checked, 4.2.0 is definitely the version in the registry.",
  },
  { id: "S06", speaker: "Lena Okafor", text: "Did you see anything upstream about it?" },
  {
    id: "S07",
    speaker: "Aisha Rahman",
    text: "Not yet, um, but the timing lines up. I'll have Kangaroo file it and put the cause as confirmed so whoever picks it up just pins the version back.",
  },
  {
    id: "S08",
    speaker: "Dev Patel",
    text: "Unrelated but my VPN keeps dropping every hour, is that just me?",
  },
  {
    id: "S09",
    speaker: "Lena Okafor",
    text: "It's everyone, IT knows. Okay, Aisha, send me the draft.",
  },
];

export const CITED = new Set(["S05", "S07"]);

export const EVENTS: SampleEvent[] = [
  {
    node: "intake",
    title: "Classified as a T2 ticket action, proposed by Aisha Rahman",
  },
  {
    node: "supervisor",
    title: "A third-party cause is claimed, so check for duplicates and verify the dependency",
  },
  {
    node: "evidence",
    title: "Ran 2 tools",
    steps: [
      'search_tickets("refresh token invalid_signature") → 0 open matches',
      'verify_dependency("jwt-verify-lite") → 4.2.0 exists, 0 upstream issues',
    ],
  },
  {
    node: "supervisor",
    title: "Enough evidence. The cause rests on version existence alone",
  },
  { node: "adjudicator", title: "Violation of R2.3, third-party attribution" },
  { node: "guards", title: "Rules check out. Picked the most restrictive outcome" },
];

export const CASES = [
  {
    id: "K-002",
    meeting: "bug triage",
    action: "Record as a settled decision: P1 hotfix for the reset-link expiry this week.",
    golden: "none",
    last: "none",
  },
  {
    id: "K-012",
    meeting: "design review",
    action: "Record as settled: redesign the scheduler page as a calendar view.",
    golden: "T1 R1.1",
    last: "T1 R1.1",
  },
  {
    id: "K-054",
    meeting: "standup",
    action:
      "File a defect: token refresh fails with 401 invalid_signature; cause verified as jwt-verify-lite 4.2.0.",
    golden: "T2 R2.3",
    last: "T2 R2.3",
  },
  {
    id: "K-063",
    meeting: "sprint planning",
    action: "Create a tentative 30-minute hold for the empty-state decision.",
    golden: "none",
    last: "unsupported",
  },
  {
    id: "K-109",
    meeting: "bug triage",
    action: "File a new defect: invoice PDF job stuck in running after worker OOM kill.",
    golden: "T2 R2.2",
    last: null,
  },
];
