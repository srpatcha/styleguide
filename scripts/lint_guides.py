#!/usr/bin/env python3
"""Style guide linter for validating documentation quality.

Checks HTML validity, broken anchors, heading structure, code block
language annotations, internal links, and formatting consistency.
Produces a summary report of all issues found.
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from html.parser import HTMLParser


class UnclosedTagChecker(HTMLParser):
    """HTML parser that tracks unclosed tags."""

    VOID_ELEMENTS = frozenset([
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    ])

    def __init__(self):
        super().__init__()
        self.tag_stack = []
        self.issues = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() not in self.VOID_ELEMENTS:
            self.tag_stack.append((tag.lower(), self.getpos()))

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in self.VOID_ELEMENTS:
            return
        if not self.tag_stack:
            self.issues.append(
                f"line {self.getpos()[0]}: unexpected closing tag </{tag}>"
            )
            return
        expected_tag, _pos = self.tag_stack[-1]
        if expected_tag == tag_lower:
            self.tag_stack.pop()
        else:
            self.issues.append(
                f"line {self.getpos()[0]}: closing </{tag}> does not match "
                f"opening <{expected_tag}>"
            )


def check_html_validity(filepath, content):
    """Check for unclosed or malformed HTML tags."""
    issues = []
    checker = UnclosedTagChecker()
    try:
        checker.feed(content)
    except Exception as exc:
        issues.append(f"{filepath}: HTML parse error: {exc}")
        return issues

    for issue in checker.issues:
        issues.append(f"{filepath}: {issue}")
    for tag, pos in checker.tag_stack:
        issues.append(f"{filepath}: line {pos[0]}: unclosed tag <{tag}>")
    return issues


def check_broken_anchors(filepath, content):
    """Find anchor references that point to non-existent IDs in the file."""
    issues = []
    # Collect all defined IDs (HTML id attributes and Markdown anchors)
    id_pattern = re.compile(r'(?:id=["\'])([^"\']+)["\']', re.IGNORECASE)
    defined_ids = set(id_pattern.findall(content))

    # Also collect Markdown-style heading anchors
    heading_pattern = re.compile(r'^#{1,6}\s+(.+)$', re.MULTILINE)
    for match in heading_pattern.finditer(content):
        heading_text = match.group(1).strip()
        # Convert heading to GitHub-style anchor
        anchor = re.sub(r'[^\w\s-]', '', heading_text.lower())
        anchor = re.sub(r'\s+', '-', anchor.strip())
        defined_ids.add(anchor)

    # Find all internal anchor references (#something)
    ref_pattern = re.compile(r'\[([^\]]*)\]\(#([^)]+)\)')
    for match in ref_pattern.finditer(content):
        link_text = match.group(1)
        anchor_ref = match.group(2)
        if anchor_ref not in defined_ids:
            line_num = content[:match.start()].count('\n') + 1
            issues.append(
                f"{filepath}: line {line_num}: broken anchor #{anchor_ref} "
                f"in link [{link_text}]"
            )
    return issues


def check_heading_structure(filepath, content):
    """Validate heading hierarchy (h1 > h2 > h3, no skipping levels)."""
    issues = []
    heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    prev_level = 0

    for match in heading_pattern.finditer(content):
        level = len(match.group(1))
        line_num = content[:match.start()].count('\n') + 1

        if prev_level > 0 and level > prev_level + 1:
            issues.append(
                f"{filepath}: line {line_num}: heading level skipped from "
                f"h{prev_level} to h{level} "
                f'("{match.group(2).strip()}")'
            )
        prev_level = level
    return issues


def check_code_blocks(filepath, content):
    """Check that fenced code blocks specify a language for syntax highlighting."""
    issues = []
    fence_pattern = re.compile(r'^(`{3,}|~{3,})[ \t]*(\S*).*$', re.MULTILINE)
    in_block = False

    for match in fence_pattern.finditer(content):
        fence = match.group(1)
        lang = match.group(2)

        if not in_block:
            # Opening fence
            if not lang:
                line_num = content[:match.start()].count('\n') + 1
                issues.append(
                    f"{filepath}: line {line_num}: fenced code block "
                    f"without language specifier"
                )
            in_block = True
        else:
            # Closing fence
            in_block = False
    return issues


def check_internal_links(filepath, content, repo_root):
    """Verify that internal links point to files that actually exist."""
    issues = []
    file_dir = os.path.dirname(filepath)

    # Match Markdown links [text](path) but not URLs or anchors
    link_pattern = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
    for match in link_pattern.finditer(content):
        link_text = match.group(1)
        target = match.group(2)

        # Skip external URLs, anchors, and mailto links
        if target.startswith(('http://', 'https://', '#', 'mailto:')):
            continue

        # Strip anchor from link target
        target_path = target.split('#')[0]
        if not target_path:
            continue

        # Resolve relative path
        abs_target = os.path.normpath(os.path.join(file_dir, target_path))

        if not os.path.exists(abs_target):
            line_num = content[:match.start()].count('\n') + 1
            issues.append(
                f"{filepath}: line {line_num}: broken internal link "
                f"[{link_text}]({target}) — file not found"
            )
    return issues


def check_formatting(filepath, content):
    """Check for trailing whitespace, consistent line endings, and other issues."""
    issues = []
    lines = content.split('\n')

    # Check for trailing whitespace (except intentional Markdown line breaks)
    for i, line in enumerate(lines, start=1):
        stripped = line.rstrip()
        trailing = len(line) - len(stripped)
        # Markdown uses two trailing spaces for <br>, allow that
        if trailing > 0 and trailing != 2:
            issues.append(
                f"{filepath}: line {i}: trailing whitespace "
                f"({trailing} space(s))"
            )

    # Check for mixed line endings
    has_crlf = '\r\n' in content
    lf_only = '\n' in content and '\r\n' not in content
    if has_crlf and lf_only:
        issues.append(f"{filepath}: mixed line endings (CRLF and LF)")

    # Check for missing newline at end of file
    if content and not content.endswith('\n'):
        issues.append(f"{filepath}: no newline at end of file")

    # Check for multiple consecutive blank lines (more than 2)
    if re.search(r'\n{4,}', content):
        issues.append(f"{filepath}: more than two consecutive blank lines")

    # Check for tabs in Markdown files
    if filepath.endswith('.md') and '\t' in content:
        tab_lines = [
            i for i, line in enumerate(lines, start=1) if '\t' in line
        ]
        issues.append(
            f"{filepath}: tabs found on line(s) "
            f"{', '.join(str(n) for n in tab_lines[:5])}"
            f"{'...' if len(tab_lines) > 5 else ''}"
        )
    return issues


def generate_report(all_issues, files_checked):
    """Generate a summary report of all issues found."""
    report_lines = []
    report_lines.append("=" * 60)
    report_lines.append("STYLE GUIDE LINT REPORT")
    report_lines.append("=" * 60)
    report_lines.append(f"Files checked: {files_checked}")
    report_lines.append(f"Total issues:  {len(all_issues)}")
    report_lines.append("-" * 60)

    if not all_issues:
        report_lines.append("No issues found. All checks passed!")
    else:
        # Group issues by file
        by_file = defaultdict(list)
        for issue in all_issues:
            # Extract filename from the issue string (before the first colon)
            parts = issue.split(": ", 1)
            fname = parts[0] if len(parts) > 1 else "unknown"
            by_file[fname].append(issue)

        for fname in sorted(by_file):
            report_lines.append(f"\n{fname}:")
            for issue in by_file[fname]:
                # Remove filename prefix for cleaner display
                msg = issue[len(fname) + 2:] if issue.startswith(fname + ": ") else issue
                report_lines.append(f"  - {msg}")

    report_lines.append("\n" + "=" * 60)
    return "\n".join(report_lines)


def find_files(repo_root, extensions):
    """Find all files matching the given extensions under repo_root."""
    matched = []
    for dirpath, _dirnames, filenames in os.walk(repo_root):
        # Skip hidden directories
        if any(part.startswith('.') for part in dirpath.split(os.sep)):
            continue
        for fname in filenames:
            if any(fname.endswith(ext) for ext in extensions):
                matched.append(os.path.join(dirpath, fname))
    return sorted(matched)


def lint_file(filepath, repo_root, checks):
    """Run all requested checks on a single file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as exc:
        return [f"{filepath}: could not read file: {exc}"]

    issues = []
    if "html" in checks and filepath.endswith((".html", ".htm")):
        issues.extend(check_html_validity(filepath, content))
    if "anchors" in checks:
        issues.extend(check_broken_anchors(filepath, content))
    if "headings" in checks:
        issues.extend(check_heading_structure(filepath, content))
    if "codeblocks" in checks:
        issues.extend(check_code_blocks(filepath, content))
    if "links" in checks:
        issues.extend(check_internal_links(filepath, content, repo_root))
    if "formatting" in checks:
        issues.extend(check_formatting(filepath, content))
    return issues


def build_parser():
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Lint style guide documentation for common issues."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Root directory or single file to lint (default: current dir)",
    )
    parser.add_argument(
        "--checks",
        nargs="+",
        default=["html", "anchors", "headings", "codeblocks", "links", "formatting"],
        choices=["html", "anchors", "headings", "codeblocks", "links", "formatting"],
        help="Which checks to run (default: all)",
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        default=[".md", ".html", ".htm"],
        help="File extensions to check (default: .md .html .htm)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the summary report, not individual issues",
    )
    return parser


def main(argv=None):
    """Entry point for the linter CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    target = os.path.abspath(args.path)

    if os.path.isfile(target):
        files = [target]
        repo_root = os.path.dirname(target)
    elif os.path.isdir(target):
        repo_root = target
        files = find_files(repo_root, args.extensions)
    else:
        print(f"Error: {args.path} is not a valid file or directory", file=sys.stderr)
        return 1

    all_issues = []
    for fpath in files:
        file_issues = lint_file(fpath, repo_root, args.checks)
        all_issues.extend(file_issues)
        if not args.quiet:
            for issue in file_issues:
                print(issue)

    report = generate_report(all_issues, len(files))
    print(report)

    return 1 if all_issues else 0


if __name__ == "__main__":
    sys.exit(main())
