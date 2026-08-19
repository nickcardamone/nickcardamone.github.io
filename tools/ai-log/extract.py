#!/usr/bin/env python3
"""Extract reviewable task segments from local Claude Code transcripts.

Read-only. Reads ~/.claude/projects/*/*.jsonl and writes a review queue to
tools/ai-log/queue/queue.json. Nothing here touches the published site: the
queue holds raw prompt text so it can be reviewed, and is gitignored.

Segmentation is deliberately rule-based rather than model-driven, so the
pipeline behind a transparency page is itself inspectable. A session is not a
task -- one session routinely spans several -- so segments are cut at:

  1. session start
  2. an explicit chapter marker (mark_chapter)
  3. an idle gap longer than --gap minutes before a typed prompt

Boundaries are reported per segment so a reviewer can merge or split them.

Usage:
  python3 tools/ai-log/extract.py            # write queue, print report
  python3 tools/ai-log/extract.py --gap 90   # looser idle threshold
  python3 tools/ai-log/extract.py --report   # print only, write nothing
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
TRANSCRIPTS = os.path.expanduser("~/.claude/projects/*/*.jsonl")
QUEUE = os.path.join(HERE, "queue", "queue.json")

# Claude Code deletes transcripts once they pass cleanupPeriodDays (default 30),
# so the live store is a rolling window, not an archive. Everything read is
# merged into a durable file; segments that age off disk are kept and marked.
REVIEWER_FIELDS = ("status", "summary", "notes",
                   "destination", "specification", "discretion", "stage", "outcome")

# The rubric. Values a reviewer may assign, and — deliberately recorded — which
# of them a machine can suggest versus which only a person can set.
#
# `specification` and `stage` are human-only on purpose. Stage was tested:
# classifying how segments open by leading verb left 87% unclassifiable, so it
# cannot be pattern-matched from prompt text and must not be faked.
RUBRIC = OrderedDict([
    ("destination", {
        "values": ["instrumental", "authored-prose", "mixed"],
        "means": "where the output lands: scaffolding, or text published under your name",
        "assigned_by": "human, with a hint from file types touched",
    }),
    ("specification", {
        "values": ["tight", "partial", "loose"],
        "means": "how much of the decision space you pinned down before asking",
        "assigned_by": "human only — the leverage hint is a weak proxy, not a score",
    }),
    ("discretion", {
        "values": ["directed", "discretionary"],
        "means": "did the agent stay inside the brief or go beyond it",
        "assigned_by": "human",
    }),
    ("stage", {
        "values": ["before", "during", "after"],
        "means": "did the agent engage before, during, or after your own artifact existed",
        "assigned_by": "human only — not derivable from transcripts",
    }),
    ("outcome", {
        "values": ["accepted", "corrected", "reverted"],
        "means": "what you did with what came back",
        "assigned_by": "human only — lexical detection was tried and abandoned; "
                       "substantive corrections read as plain assertions",
    }),
])

# Blunt rejection cues only. This does NOT detect correction in general, and
# the attempt to make it do so was abandoned rather than overfitted: the
# clearest correction in this archive -- "we coded the 73 ourselves - so you
# did retrieve that" -- is phrased as a statement of fact and matches nothing
# lexical. Substantive corrections usually look like calm assertions.
#
# So `outcome` is a human-assigned field. This count is a pointer to segments
# worth opening first, and a zero carries no information.
PUSHBACK = re.compile(
    r"^\W*(no\b|nope|actually|wait\b|not quite|incorrect|revert|undo|stop"
    r"|instead|i disagree|that'?s (wrong|not right|backwards))",
    re.I,
)

PROSE_EXT = {".md", ".markdown", ".txt", ".rst", ".tex", ".docx"}
CODE_EXT = {".py", ".js", ".css", ".html", ".sh", ".sql", ".r", ".yml", ".yaml",
            ".json", ".rb", ".do", ".sas", ".ipynb"}

PROMPT_CAP = 2000  # keep the queue readable; one prompt in the wild hit 175k

# How each project directory should be described publicly. Anything not listed
# falls back to the most restrictive label rather than the most convenient one,
# so a new clinical project is never mislabelled as personal by omission.
PROJECT_TYPES = {
    "proj-website": "personal-site",
}
DEFAULT_PROJECT_TYPE = "clinical-analysis"

# Redacted in the queue itself -- there is no reason to keep a live credential
# sitting in a working file, even a gitignored one.
CREDENTIAL = re.compile(
    r"\b(gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,})"
)

# Surfaced per segment so review effort goes where the risk is.
RISK = OrderedDict(
    [
        ("credential", CREDENTIAL),
        ("identifier", re.compile(r"\d{5,}")),
        ("date", re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")),
        (
            "clinical",
            re.compile(
                r"\b(patient|subject|mrn|encounter|admission|discharge|troponin"
                r"|stroke|nihss|icd|cpt|ehr|emr|cohort|diagnos\w*|comorbid\w*"
                r"|mortality)\b",
                re.I,
            ),
        ),
        ("query", re.compile(r"\b(select |from |join |where |group by)\b", re.I)),
        ("path", re.compile(r"/Users/\w+")),
        ("email", re.compile(r"[\w.+-]+@[\w-]+\.\w+")),
    ]
)


def human_gap(delta):
    """Most 'idle gaps' are the same session picked up days later."""
    minutes = round(delta.total_seconds() / 60)
    if minutes < 90:
        return "%dm" % minutes
    if minutes < 60 * 36:
        return "%dh" % round(minutes / 60)
    return "%dd" % round(minutes / 1440)


def parse_ts(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def text_of(message):
    """User content arrives as a bare string or a list of typed blocks."""
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content if isinstance(b, dict)
        )
    return ""


def read_events(path):
    """Yield the records we care about, in file order."""
    project = os.path.basename(os.path.dirname(path)).split("-Desktop-")[-1]
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue

        stamp = parse_ts(record.get("timestamp"))
        kind = record.get("type")

        if kind == "user" and record.get("promptSource"):
            body = text_of(record.get("message"))
            if not body.strip():
                # Attachment- or image-only turns carry no text to review.
                yield {"what": "empty", "at": stamp, "project": project,
                       "session": record.get("sessionId")}
                continue
            yield {
                "what": "prompt",
                "at": stamp,
                "project": project,
                "session": record.get("sessionId"),
                "text": body,
                "branch": record.get("gitBranch"),
            }

        elif kind == "assistant":
            message = record.get("message") or {}
            for block in message.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                yield {
                    "what": "tool",
                    "at": stamp,
                    "project": project,
                    "session": record.get("sessionId"),
                    "name": block.get("name"),
                    "input": block.get("input") or {},
                }

        if record.get("attributionMcpTool") == "mark_chapter":
            yield {
                "what": "chapter",
                "at": stamp,
                "project": project,
                "session": record.get("sessionId"),
            }


def redact(text):
    return CREDENTIAL.sub("[REDACTED CREDENTIAL]", text)


def scan_risk(blob):
    found = OrderedDict()
    for name, pattern in RISK.items():
        hits = len(pattern.findall(blob))
        if hits:
            found[name] = hits
    return found


class Segment(object):
    def __init__(self, project, session, started, reason):
        self.project = project
        self.session = session
        self.started = started
        self.ended = started
        self.reason = reason
        self.prompts = []
        self.empty_turns = 0
        self.tools = Counter()
        self.files = set()
        self.commits = []

    def touch(self, when):
        if when and (self.ended is None or when > self.ended):
            self.ended = when

    def add_tool(self, name, payload):
        self.tools[name] += 1
        path = payload.get("file_path")
        if path:
            self.files.add(os.path.relpath(path, REPO) if path.startswith(REPO) else path)
        command = payload.get("command") or ""
        if "git commit" in command:
            self.commits.append(command.strip().splitlines()[0][:120])

    def duration(self):
        if not (self.started and self.ended):
            return 0
        return round((self.ended - self.started).total_seconds() / 60)

    def to_dict(self):
        prompts = [redact(p)[:PROMPT_CAP] for p in self.prompts]
        blob = "\n".join(prompts)
        return OrderedDict(
            [
                ("id", "%s-%s" % (
                    self.started.strftime("%Y%m%dT%H%M") if self.started else "unknown",
                    (self.session or "nosession")[:8],
                )),
                ("project", self.project),
                ("project_type", PROJECT_TYPES.get(self.project, DEFAULT_PROJECT_TYPE)),
                ("started", self.started.isoformat() if self.started else None),
                ("duration_min", self.duration()),
                ("boundary", self.reason),
                ("prompt_count", len(self.prompts)),
                ("untexted_turns", self.empty_turns),
                # Rule-based cuts over-segment; flagging the likely fragments
                # is cheaper for a reviewer than re-reading every boundary.
                ("hint", "short — may belong with the previous segment"
                 if len(self.prompts) == 1 and self.duration() < 2 else ""),
                ("tool_calls", sum(self.tools.values())),
                ("top_tools", [k for k, _ in self.tools.most_common(5)]),
                ("files_touched", sorted(self.files)[:25]),
                ("commits", self.commits),
                ("risk", scan_risk(blob)),
                # Machine signals. Deliberately separate from the reviewer's
                # fields so nothing computed is mistaken for a judgment.
                ("hints", self.hints()),
                # For review only. Never copy this field to anything published.
                ("prompts", prompts),
                # Filled in by the reviewer. Empty means not yet judged.
                ("status", "pending"),
                ("summary", ""),
                ("destination", ""),
                ("specification", ""),
                ("discretion", ""),
                ("stage", ""),
                ("outcome", ""),
                ("notes", ""),
            ]
        )

    def hints(self):
        # Only files inside the repo are work product. Scratch files, Claude's
        # own memory notes, and anything read out of ~/Downloads would otherwise
        # show up as prose you authored.
        owned = [f for f in self.files if not f.startswith("/")]
        prose = sorted(f for f in owned if os.path.splitext(f)[1].lower() in PROSE_EXT)
        code = sorted(f for f in owned if os.path.splitext(f)[1].lower() in CODE_EXT)
        pushback = sum(1 for p in self.prompts if PUSHBACK.search(p.strip()[:200]))
        return OrderedDict([
            # Actions taken per instruction given. High values mean you said
            # little and a lot happened -- a proxy for delegated latitude, not
            # a measure of it.
            ("leverage", round(sum(self.tools.values()) / max(len(self.prompts), 1), 1)),
            ("pushback_turns", pushback),
            ("pushback_recall", "blunt rejections only — a zero carries no information"),
            ("prose_files", prose[:10]),
            ("code_files", code[:10]),
            ("external_files", len([f for f in self.files if f.startswith("/")])),
            ("commits", len(self.commits)),
        ])


def build_segments(gap_minutes):
    events = []
    for path in glob.glob(TRANSCRIPTS):
        events.extend(read_events(path))
    events.sort(key=lambda e: (e["session"] or "", e["at"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc)))

    segments = []
    current = None
    last_at = None
    gap = dt.timedelta(minutes=gap_minutes)

    for event in events:
        session = event["session"]
        when = event["at"]

        if current is None or current.session != session:
            reason = "session start"
            current = None
        elif event["what"] == "chapter":
            # A chapter marker means the work itself changed topic.
            current.pending_break = "chapter marker"
            continue
        elif event["what"] == "prompt" and last_at and when and when - last_at > gap:
            reason = "resumed after %s" % human_gap(when - last_at)
            current = None
        elif event["what"] == "prompt" and getattr(current, "pending_break", None):
            reason = current.pending_break
            current = None
        else:
            reason = None

        if current is None:
            current = Segment(event["project"], session, when, reason or "session start")
            segments.append(current)

        current.touch(when)
        if event["what"] == "prompt":
            current.prompts.append(event["text"])
        elif event["what"] == "empty":
            current.empty_turns += 1
        elif event["what"] == "tool":
            current.add_tool(event["name"], event["input"])
        last_at = when or last_at

    # A segment with no typed prompt is tool fallout from the previous one.
    return [s for s in segments if s.prompts]


def merge_archive(rows):
    """Fold this run into the durable store, preserving reviewer decisions.

    Returns (merged rows, count new, count aged off disk).
    """
    existing = OrderedDict()
    if os.path.exists(QUEUE):
        with open(QUEUE, encoding="utf-8") as handle:
            for row in json.load(handle).get("segments", []):
                existing[row["id"]] = row

    seen = set()
    added = 0
    for row in rows:
        seen.add(row["id"])
        prior = existing.get(row["id"])
        if prior is None:
            added += 1
            row["first_seen"] = dt.datetime.now().isoformat(timespec="seconds")
            existing[row["id"]] = row
            continue
        # Refresh the derived fields, keep whatever the reviewer wrote.
        keep = {f: prior.get(f, "") for f in REVIEWER_FIELDS}
        row["first_seen"] = prior.get("first_seen")
        row.update(keep)
        row["on_disk"] = True
        existing[row["id"]] = row

    gone = 0
    for key, row in existing.items():
        if key in seen:
            row["on_disk"] = True
        elif row.get("on_disk", True):
            row["on_disk"] = False
            row["aged_off"] = dt.datetime.now().isoformat(timespec="seconds")
            gone += 1

    merged = sorted(existing.values(), key=lambda r: r.get("started") or "")
    return merged, added, gone


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gap", type=int, default=60, help="idle minutes that start a new task (default 60)")
    ap.add_argument("--report", action="store_true", help="print only, do not write the queue")
    args = ap.parse_args()

    segments = build_segments(args.gap)
    if not segments:
        print("No transcripts found under ~/.claude/projects/", file=sys.stderr)
        return 1

    rows = [s.to_dict() for s in segments]
    sessions = len(set(s.session for s in segments))
    prompts = sum(len(s.prompts) for s in segments)
    flagged = [r for r in rows if r["risk"]]

    payload = OrderedDict(
        [
            ("generated", dt.datetime.now().isoformat(timespec="seconds")),
            ("rubric", RUBRIC),
            (
                "coverage",
                OrderedDict(
                    [
                        ("note", "Claude Code sessions on this machine only; claude.ai chats are not included"),
                        ("projects", len(set(s.project for s in segments))),
                        ("sessions", sessions),
                        ("segments", len(segments)),
                        ("prompts", prompts),
                        ("first", min(r["started"] for r in rows if r["started"])),
                        ("last", max(r["started"] for r in rows if r["started"])),
                    ]
                ),
            ),
            ("segments", rows),
        ]
    )

    untexted = sum(s.empty_turns for s in segments)
    fragments = sum(1 for r in rows if r["hint"])
    print("%d task segments from %d sessions (%d typed prompts)" % (len(segments), sessions, prompts))
    print("%d segments carry at least one risk flag" % len(flagged))
    print("%d look like fragments to merge; %d turns had no reviewable text\n" % (fragments, untexted))

    by_project = Counter(r["project"] for r in rows)
    for name, count in by_project.most_common():
        print("  %-22s %2d segments  [%s]" % (name, count, PROJECT_TYPES.get(name, DEFAULT_PROJECT_TYPE)))

    print("\n%-16s %-22s %5s %5s  %-18s %s" % ("WHEN", "PROJECT", "PRMT", "MIN", "BOUNDARY", "RISK"))
    for r in sorted(rows, key=lambda r: r["started"] or ""):
        when = (r["started"] or "")[:16].replace("T", " ")
        risk = ",".join("%s:%d" % (k, v) for k, v in r["risk"].items()) or "-"
        print("%-16s %-22s %5d %5d  %-18s %s" % (when, r["project"], r["prompt_count"], r["duration_min"], r["boundary"], risk))

    if args.report:
        return 0

    merged, added, gone = merge_archive(rows)
    payload["segments"] = merged
    payload["coverage"]["archived_segments"] = len(merged)
    payload["coverage"]["retention_note"] = (
        "Claude Code deletes transcripts after cleanupPeriodDays (default 30); "
        "segments no longer on disk are retained here with on_disk=false"
    )

    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    with open(QUEUE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False)
        handle.write("\n")

    print("\narchive: %d segments (%d new this run, %d aged off disk)" % (len(merged), added, gone))
    pending = sum(1 for r in merged if r.get("status") == "pending")
    print("%d pending review\n" % pending)

    print("rubric coverage:")
    for field in RUBRIC:
        done = sum(1 for r in merged if r.get(field))
        print("  %-14s %3d/%d marked   (%s)" % (
            field, done, len(merged), RUBRIC[field]["assigned_by"].split(" —")[0]))

    pushy = [r for r in merged if r["hints"]["pushback_turns"]]
    prose = [r for r in merged if r["hints"]["prose_files"]]
    print("\n%d segments show pushback turns (candidates for outcome=corrected)" % len(pushy))
    print("%d segments touched prose files (candidates for destination review)" % len(prose))
    print("wrote %s (gitignored -- holds raw prompt text)" % os.path.relpath(QUEUE, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
