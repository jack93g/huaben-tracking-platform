"""Post an automated code review comment on a PR using DeepSeek via OpenRouter.

Adapted from the app repo (jack93g/project-chinese-story-generator) for this
infrastructure repo (D-011). Run from GitHub Actions (see
.github/workflows/pr-review.yml). Reads
its configuration from environment variables so it needs no CLI arguments:

    OPENROUTER_API_KEY  OpenRouter API key (repo secret)
    GITHUB_TOKEN        Token with pull-requests: write (Actions provides this)
    GITHUB_REPOSITORY   "owner/repo" (Actions provides this)
    PR_NUMBER           Pull request number to review
    PR_HEAD_SHA         SHA of the PR's head commit (Actions provides this)
    GITHUB_BASE_REF     PR base branch (Actions provides this for pull_request
                         events); CLAUDE.md is read from here, not the PR
                         branch, so a PR can't rewrite the review criteria
                         it's judged against

The model is prompted to return a small JSON object (verdict/summary/
findings) which is rendered into a fixed comment template here, rather than
trusting it to produce well-formed markdown directly. Each posted comment
carries a hidden `<!-- deepseek-review-sha: ... -->` marker with the SHA it
reviewed; on a later push, the previous marker is used to also diff and
summarize what changed since that last review.

The PR diff itself is still attacker-controlled text fed to the model, so
its output is a suggestion for a human to weigh, not something acted on
automatically. The workflow checks out the PR's base SHA (not the PR's own
code) before running this script, so a PR cannot modify the script itself
to exfiltrate the secrets in its environment.

Uses only the standard library so the workflow needs no pip install step.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GITHUB_API = "https://api.github.com"
OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
# Verified against OpenRouter's live /models catalog on 2026-09-11.
OPENROUTER_MODEL = "deepseek/deepseek-v4.1-flash"
MAX_DIFF_CHARS = 60_000
REQUEST_TIMEOUT = 30
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4

REVIEW_MARKER_PREFIX = "<!-- deepseek-review-sha: "
SHA_PATTERN = re.compile(r"[0-9a-fA-F]{7,40}")
VERDICT_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴"}

REVIEW_SYSTEM_PROMPT = """\
You are an independent reviewer for a public infrastructure repository: \
Terraform on Google Cloud, GitHub Actions workflows, server-side Google Tag \
Manager, BigQuery, and dbt. You are reviewing a pull request diff. Below is \
the project's CLAUDE.md, documenting its architecture and rules - use it to \
judge whether the change follows them.

<CLAUDE.md>
{claude_md}
</CLAUDE.md>

Review the diff for:
- Security: IAM broader than needed, roles granted to individuals instead of \
groups, service account keys, public access, workflows with more \
permissions than they need (especially id-token: write outside the Terraform \
workflows), actions not pinned to a full commit SHA, untrusted code running \
with secrets
- Privilege escalation by CI identities (infra/bootstrap/ci.tf and any IAM \
for service accounts): roles this diff adds or broadens that let an account \
grant itself more access (Project IAM Admin without a modifiedGrantsByRole \
condition, Owner, Editor, Security Admin, Service Account Token Creator, \
Service Account Admin or User beyond what's needed), or that are added \
before any resource in the repo needs them. Only flag grants the diff adds \
or broadens, not existing ones it leaves unchanged.
- Secrets in Terraform state or plan output: secret values passed as regular \
attributes instead of write-only arguments (e.g. secret_data_wo) or ephemeral \
resources, outputs exposing secrets, nonsensitive() on sensitive values. PR \
plans run the PR's own code with state access and print to public logs.
- Code that runs during terraform plan with CI credentials: external data \
sources, local-exec or other provisioners, new data sources reading secrets \
or state (e.g. terraform_remote_state)
- Workflow trust boundaries: jobs that run PR-controlled code while holding \
secrets or an OIDC token beyond the read-only plan accounts, apply jobs \
reachable without their GitHub Environment, weakened branch or environment \
conditions
- Anything this public repo must not contain: account names, organization, \
billing account or customer IDs, secrets or tokens
- Terraform correctness: changes that would destroy or replace resources, \
missing dependencies, unpinned providers, resources outside EU locations
- Correctness bugs in scripts, SQL, and workflow logic
- Missing documentation or decision records the CLAUDE.md rules require

Do not comment on formatting or style a linter would catch.

If the diff ends with a note listing files that were omitted because the \
diff was too large, you have not seen those files: do not guess at their \
contents, and say in "findings_markdown" that they were not reviewed.

The user message may also include a second diff showing what changed since \
a previous review of this same PR. If it does, use it to fill in \
"changes_since_last_review_markdown" below, focused on whether it addresses \
issues a reviewer would have raised on the first diff. If it doesn't, set \
that field to null.

Respond with ONLY a single JSON object, no markdown code fence and no prose \
outside it, with exactly these keys:
{{
  "verdict": "green" | "yellow" | "red",
  "pr_summary": string, 1-3 plain sentences on what this PR does,
  "findings_markdown": string, a markdown bullet list of specific findings \
with file names, or one sentence saying none were found,
  "changes_since_last_review_markdown": string or null, per the rule above
}}

verdict guide: green = nothing worth a human's attention; yellow = minor \
issues or missing documentation, not blocking; red = a correctness bug, a \
security issue, a leak of something this public repo must not contain, or a \
change that would destroy or replace infrastructure.
"""


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cutoff = text.rfind("\n", 0, max_chars)
    if cutoff == -1:
        cutoff = max_chars
    return text[:cutoff] + "\n\n... [truncated, too large to review in full]"


SOURCE_PREFIXES = (
    "infra/",
    ".github/",
    "scripts/",
    "contract/",
    "dbt/",
)
# Security-relevant configuration outside those folders.
SOURCE_FILES = {"mise.toml", ".pre-commit-config.yaml", ".tflint.hcl"}
TEST_FILE_PATTERN = re.compile(
    r"(^|/)(tests?/|__tests__/)|(^|/)test_[^/]*\.py$|\.(test|spec)\.[jt]sx?$"
)
LOW_PRIORITY_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    ".terraform.lock.hcl",
}
# Generated GTM container exports: large, and reviewed in the GTM UI.
LOW_PRIORITY_PREFIXES = ("gtm/",)


def file_priority(path: str) -> int:
    """Rank a changed file for review: 0 source, 1 other, 2 tests, 3 docs/lockfiles.

    Source is Terraform, workflows, scripts, the tracking contract, and dbt.
    "Other" (e.g. pyproject.toml) ranks above tests: it is usually small and
    often security-relevant. Tests are checked before source so a test file
    inside a source folder isn't ranked as source.
    """
    name = path.rsplit("/", 1)[-1]
    if (
        path.startswith("docs/")
        or name.lower().endswith(".md")
        or name in LOW_PRIORITY_NAMES
        or path.startswith(LOW_PRIORITY_PREFIXES)
    ):
        return 3
    if TEST_FILE_PATTERN.search(path):
        return 2
    if path in SOURCE_FILES or path.startswith(SOURCE_PREFIXES):
        return 0
    return 1


def diff_file_path(section: str) -> str:
    """Return the post-change path from a section's `diff --git a/X b/Y` header."""
    header = section.split("\n", 1)[0].removeprefix("diff --git ")

    def unprefix(path: str) -> str:
        # Git quotes paths containing unusual characters: "b/some path".
        return path.strip('"')[2:]

    # Unrenamed files repeat the same path twice, which stays unambiguous
    # even when the path itself contains " b/".
    half = (len(header) - 1) // 2
    old_path, sep, new_path = header[:half], header[half : half + 1], header[half + 1 :]
    if sep == " " and unprefix(old_path) == unprefix(new_path):
        return unprefix(new_path)
    start = max(header.rfind(" b/"), header.rfind(' "b/'))
    return unprefix(header[start + 1 :]) if start != -1 else header


def split_diff_by_file(diff: str) -> list[str]:
    """Split a unified diff into one section per `diff --git` header."""
    return [section for section in re.split(r"(?m)^(?=diff --git )", diff) if section]


def fit_diff_to_budget(diff: str, max_chars: int) -> tuple[str, list[str]]:
    """Fit a diff into max_chars by dropping whole files, lowest priority first.

    Diffs arrive in alphabetical file order, so a plain cut would keep docs
    and drop backend code. Instead, whole files are kept in priority order
    (source, other, tests, docs/lockfiles; ties keep diff order) until the
    budget is used, skipping any file that doesn't fit in what's left. The
    kept files are returned with a note listing the omitted paths appended
    (the note itself isn't counted against the budget), plus that list.
    """
    if len(diff) <= max_chars:
        return diff, []
    sections = split_diff_by_file(diff)
    if len(sections) <= 1 or not sections[0].startswith("diff --git "):
        # Not a multi-file git diff; fall back to a plain line-boundary cut.
        return truncate(diff, max_chars), []

    kept: list[str] = []
    omitted: list[str] = []
    remaining = max_chars
    for section in sorted(sections, key=lambda s: file_priority(diff_file_path(s))):
        if len(section) <= remaining:
            kept.append(section)
            remaining -= len(section)
        else:
            omitted.append(diff_file_path(section))

    text = "".join(kept)
    if omitted:
        if text and not text.endswith("\n"):
            text += "\n"
        text += (
            f"\n... [{len(omitted)} file(s) omitted, too large to review in full. "
            "These files were NOT reviewed:\n"
            + "\n".join(f"- {path}" for path in omitted)
            + "\n]"
        )
    return text, omitted


def github_request(url: str, token: str, accept: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def fetch_pr_diff(repo: str, pr_number: str, token: str) -> tuple[str, list[str]]:
    """Return the PR diff fitted to MAX_DIFF_CHARS and the paths left out of it."""
    if not pr_number.isdigit():
        raise ValueError(f"PR_NUMBER must be numeric, got: {pr_number!r}")
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}"
    diff = github_request(url, token, "application/vnd.github.v3.diff").decode("utf-8")
    return fit_diff_to_budget(diff, MAX_DIFF_CHARS)


def fetch_diff_since(repo: str, prev_sha: str, head_sha: str, token: str) -> str:
    url = f"{GITHUB_API}/repos/{repo}/compare/{prev_sha}...{head_sha}"
    diff = github_request(url, token, "application/vnd.github.v3.diff").decode("utf-8")
    return fit_diff_to_budget(diff, MAX_DIFF_CHARS)[0]


def load_claude_md(repo: str, token: str, base_ref: str) -> str:
    url = f"{GITHUB_API}/repos/{repo}/contents/CLAUDE.md?ref={urllib.parse.quote(base_ref, safe='')}"
    try:
        return github_request(url, token, "application/vnd.github.v3.raw").decode(
            "utf-8"
        )
    except urllib.error.HTTPError as error:
        if error.code == 404:
            print(
                f"Warning: no CLAUDE.md found at ref {base_ref!r}, "
                "reviewing without repo-specific context.",
                file=sys.stderr,
            )
            return "(no CLAUDE.md found in this repo)"
        raise


def fetch_last_reviewed_sha(repo: str, pr_number: str, token: str) -> str | None:
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments?per_page=100"
    comments = json.loads(github_request(url, token, "application/vnd.github+json"))
    for comment in reversed(comments):
        # Only trust comments actually posted by this workflow's token - anyone
        # with comment access could otherwise write a fake marker themselves.
        if (comment.get("user") or {}).get("login") != "github-actions[bot]":
            continue
        body = comment.get("body") or ""
        if REVIEW_MARKER_PREFIX not in body:
            continue
        # rsplit, not split: a prompt-injected diff could trick the model into
        # writing marker-shaped text earlier in its own findings. Our real
        # marker is always the one this script appended last.
        tail = body.rsplit(REVIEW_MARKER_PREFIX, 1)[1]
        sha = tail.split("-->", 1)[0].strip()
        if SHA_PATTERN.fullmatch(sha):
            return sha
    return None


def call_openrouter(
    api_key: str, diff: str, claude_md: str, since_diff: str | None = None
) -> str:
    system_prompt = REVIEW_SYSTEM_PROMPT.format(claude_md=claude_md)
    user_content = f"Review this pull request diff:\n\n<diff>\n{diff}\n</diff>"
    if since_diff:
        user_content += (
            "\n\nHere is what changed since the previous review of this PR:"
            f"\n\n<changes_since_last_review>\n{since_diff}\n</changes_since_last_review>"
        )

    body = json.dumps(
        {
            "model": OPENROUTER_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        OPENROUTER_API,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/jack93g/huaben-tracking-platform",
            "X-Title": "huaben-tracking-platform PR review",
        },
        method="POST",
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code in RETRY_STATUS_CODES and attempt < MAX_ATTEMPTS:
                wait = 2**attempt
                print(
                    f"OpenRouter API returned {error.code} (attempt {attempt}/{MAX_ATTEMPTS}), "
                    f"retrying in {wait}s: {detail}",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            print(f"OpenRouter API error {error.code}: {detail}", file=sys.stderr)
            raise
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt < MAX_ATTEMPTS:
                wait = 2**attempt
                print(
                    f"OpenRouter request failed ({error}) (attempt {attempt}/{MAX_ATTEMPTS}), "
                    f"retrying in {wait}s",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            raise

        try:
            payload = json.loads(raw)
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError(f"content is {type(content).__name__}, not str")
            return content
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise RuntimeError(
                f"Unexpected OpenRouter response shape: {raw.decode('utf-8', errors='replace')}"
            ) from error

    raise RuntimeError("unreachable")


def extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)


def parse_review(content: str) -> dict:
    try:
        data = extract_json_object(content)
        verdict = data["verdict"]
        if not isinstance(verdict, str) or verdict.lower() not in VERDICT_EMOJI:
            raise ValueError(f"unexpected verdict: {verdict!r}")
        pr_summary = data["pr_summary"]
        findings_markdown = data["findings_markdown"]
        if not isinstance(pr_summary, str) or not isinstance(findings_markdown, str):
            raise ValueError("pr_summary/findings_markdown must be strings")
        since = data.get("changes_since_last_review_markdown")
        if since is not None and not isinstance(since, str):
            raise ValueError(
                "changes_since_last_review_markdown must be a string or null"
            )
        return {
            "verdict": verdict.lower(),
            "pr_summary": pr_summary,
            "findings_markdown": findings_markdown,
            "changes_since_last_review_markdown": since or None,
        }
    except (json.JSONDecodeError, KeyError, ValueError) as error:
        raise RuntimeError(f"Unexpected review JSON shape: {content}") from error


def render_comment(
    review: dict, model: str, head_sha: str, omitted_files: list[str] | None = None
) -> str:
    emoji = VERDICT_EMOJI[review["verdict"]]
    lines = [
        f"### {emoji} DeepSeek review",
        "",
        f"**Summary:** {review['pr_summary']}",
        "",
        "**Findings:**",
        "",
        review["findings_markdown"],
    ]

    if omitted_files:
        # Stated here as well as in the prompt so the comment reliably says
        # what wasn't reviewed, whatever the model wrote. Backticks are
        # stripped so a crafted filename can't break out of the code span.
        paths = ", ".join(f"`{path.replace('`', '')}`" for path in omitted_files)
        lines += [
            "",
            f"**Not reviewed** (omitted to fit the {MAX_DIFF_CHARS:,}-character "
            f"diff limit): {paths}",
        ]

    since = review["changes_since_last_review_markdown"]
    if since:
        lines += [
            "",
            "---",
            "",
            "**What changed since the last review:**",
            "",
            since,
        ]

    lines += [
        "",
        "---",
        "",
        "_Automated, unverified output generated from this PR's diff - "
        "weigh it like a first-pass opinion, not a verdict._",
        "",
        f"_Review generated by `{model}` via OpenRouter_",
        f"{REVIEW_MARKER_PREFIX}{head_sha} -->",
    ]
    return "\n".join(lines)


def post_comment(repo: str, pr_number: str, token: str, comment_body: str) -> None:
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    request = urllib.request.Request(
        url,
        data=json.dumps({"body": comment_body}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT):
        pass


def main() -> None:
    openrouter_api_key = env("OPENROUTER_API_KEY")
    github_token = env("GITHUB_TOKEN")
    repo = env("GITHUB_REPOSITORY")
    pr_number = env("PR_NUMBER")
    head_sha = env("PR_HEAD_SHA")
    base_ref = os.environ.get("GITHUB_BASE_REF") or "main"

    diff, omitted_files = fetch_pr_diff(repo, pr_number, github_token)
    if not diff.strip():
        print("Empty diff, nothing to review.")
        return

    claude_md = load_claude_md(repo, github_token, base_ref)

    since_diff = None
    last_sha = fetch_last_reviewed_sha(repo, pr_number, github_token)
    if last_sha and last_sha != head_sha:
        try:
            since_diff = (
                fetch_diff_since(repo, last_sha, head_sha, github_token) or None
            )
        except urllib.error.HTTPError as error:
            print(
                f"Warning: could not diff against previous review ({last_sha}): {error}",
                file=sys.stderr,
            )

    content = call_openrouter(openrouter_api_key, diff, claude_md, since_diff)
    review = parse_review(content)
    comment = render_comment(review, OPENROUTER_MODEL, head_sha, omitted_files)
    post_comment(repo, pr_number, github_token, comment)
    print("Posted DeepSeek review comment.")


if __name__ == "__main__":
    main()
