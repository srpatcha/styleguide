"""Tests for lint_guides.py style guide linter."""

import os
import tempfile

import pytest

from lint_guides import (
    build_parser,
    check_broken_anchors,
    check_code_blocks,
    check_formatting,
    check_heading_structure,
    check_html_validity,
    check_internal_links,
    find_files,
    generate_report,
    lint_file,
    main,
)


# ---------------------------------------------------------------------------
# check_html_validity
# ---------------------------------------------------------------------------


class TestCheckHtmlValidity:
    def test_valid_html(self):
        html = "<div><p>Hello</p></div>"
        assert check_html_validity("test.html", html) == []

    def test_unclosed_tag(self):
        html = "<div><p>Hello</div>"
        issues = check_html_validity("test.html", html)
        assert len(issues) >= 1
        assert "does not match" in issues[0] or "unclosed" in issues[0]

    def test_void_elements_ok(self):
        html = "<br><hr><img src='x'><input>"
        assert check_html_validity("test.html", html) == []

    def test_unexpected_closing_tag(self):
        html = "</span>"
        issues = check_html_validity("test.html", html)
        assert any("unexpected closing" in i for i in issues)


# ---------------------------------------------------------------------------
# check_broken_anchors
# ---------------------------------------------------------------------------


class TestCheckBrokenAnchors:
    def test_valid_anchor(self):
        content = "# My Heading\n\nSee [link](#my-heading)"
        issues = check_broken_anchors("test.md", content)
        assert issues == []

    def test_broken_anchor(self):
        content = "# Intro\n\nSee [link](#nonexistent)"
        issues = check_broken_anchors("test.md", content)
        assert len(issues) == 1
        assert "nonexistent" in issues[0]

    def test_html_id_anchor(self):
        content = '<a id="foo"></a>\n\nSee [link](#foo)'
        issues = check_broken_anchors("test.md", content)
        assert issues == []


# ---------------------------------------------------------------------------
# check_heading_structure
# ---------------------------------------------------------------------------


class TestCheckHeadingStructure:
    def test_proper_hierarchy(self):
        content = "# H1\n## H2\n### H3\n"
        assert check_heading_structure("test.md", content) == []

    def test_skipped_level(self):
        content = "# H1\n### H3\n"
        issues = check_heading_structure("test.md", content)
        assert len(issues) == 1
        assert "skipped" in issues[0]

    def test_multiple_skips(self):
        content = "# H1\n#### H4\n"
        issues = check_heading_structure("test.md", content)
        assert len(issues) == 1
        assert "h1 to h4" in issues[0]


# ---------------------------------------------------------------------------
# check_code_blocks
# ---------------------------------------------------------------------------


class TestCheckCodeBlocks:
    def test_with_language(self):
        content = "```python\nprint('hi')\n```\n"
        assert check_code_blocks("test.md", content) == []

    def test_without_language(self):
        content = "```\nsome code\n```\n"
        issues = check_code_blocks("test.md", content)
        assert len(issues) == 1
        assert "without language" in issues[0]

    def test_tilde_fence_with_language(self):
        content = "~~~javascript\nconsole.log('hi');\n~~~\n"
        assert check_code_blocks("test.md", content) == []


# ---------------------------------------------------------------------------
# check_internal_links
# ---------------------------------------------------------------------------


class TestCheckInternalLinks:
    def test_valid_internal_link(self, tmp_path):
        target = tmp_path / "other.md"
        target.write_text("# Other")
        source = tmp_path / "source.md"
        content = "[link](other.md)"
        issues = check_internal_links(str(source), content, str(tmp_path))
        assert issues == []

    def test_broken_internal_link(self, tmp_path):
        source = tmp_path / "source.md"
        content = "[link](missing.md)"
        issues = check_internal_links(str(source), content, str(tmp_path))
        assert len(issues) == 1
        assert "not found" in issues[0]

    def test_external_link_ignored(self, tmp_path):
        source = tmp_path / "source.md"
        content = "[link](https://example.com)"
        issues = check_internal_links(str(source), content, str(tmp_path))
        assert issues == []

    def test_anchor_only_link_ignored(self, tmp_path):
        source = tmp_path / "source.md"
        content = "[link](#section)"
        issues = check_internal_links(str(source), content, str(tmp_path))
        assert issues == []


# ---------------------------------------------------------------------------
# check_formatting
# ---------------------------------------------------------------------------


class TestCheckFormatting:
    def test_clean_file(self):
        content = "Hello world\nSecond line\n"
        assert check_formatting("test.md", content) == []

    def test_trailing_whitespace(self):
        content = "Hello   \nworld\n"
        issues = check_formatting("test.md", content)
        assert any("trailing whitespace" in i for i in issues)

    def test_two_trailing_spaces_allowed(self):
        # Markdown line break (exactly 2 trailing spaces)
        content = "Hello  \nworld\n"
        issues = check_formatting("test.md", content)
        trailing_issues = [i for i in issues if "trailing whitespace" in i]
        assert trailing_issues == []

    def test_no_newline_at_eof(self):
        content = "Hello world"
        issues = check_formatting("test.md", content)
        assert any("no newline at end of file" in i for i in issues)

    def test_tabs_in_markdown(self):
        content = "\tindented\n"
        issues = check_formatting("test.md", content)
        assert any("tabs" in i for i in issues)

    def test_tabs_in_html_ok(self):
        content = "\tindented\n"
        issues = check_formatting("test.html", content)
        tab_issues = [i for i in issues if "tabs" in i]
        assert tab_issues == []

    def test_excessive_blank_lines(self):
        content = "Hello\n\n\n\nworld\n"
        issues = check_formatting("test.md", content)
        assert any("consecutive blank lines" in i for i in issues)


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_no_issues(self):
        report = generate_report([], 5)
        assert "No issues found" in report
        assert "Files checked: 5" in report

    def test_with_issues(self):
        issues = [
            "file.md: line 1: trailing whitespace",
            "file.md: line 5: broken anchor",
        ]
        report = generate_report(issues, 1)
        assert "Total issues:  2" in report
        assert "file.md" in report


# ---------------------------------------------------------------------------
# find_files
# ---------------------------------------------------------------------------


class TestFindFiles:
    def test_finds_markdown(self, tmp_path):
        (tmp_path / "a.md").write_text("# A")
        (tmp_path / "b.txt").write_text("B")
        (tmp_path / "c.html").write_text("<p>C</p>")
        files = find_files(str(tmp_path), [".md"])
        assert len(files) == 1
        assert files[0].endswith("a.md")

    def test_finds_multiple_extensions(self, tmp_path):
        (tmp_path / "a.md").write_text("# A")
        (tmp_path / "b.html").write_text("<p>B</p>")
        files = find_files(str(tmp_path), [".md", ".html"])
        assert len(files) == 2


# ---------------------------------------------------------------------------
# lint_file
# ---------------------------------------------------------------------------


class TestLintFile:
    def test_lint_clean_md(self, tmp_path):
        f = tmp_path / "clean.md"
        f.write_text("# Title\n\n## Section\n\nHello world.\n")
        issues = lint_file(str(f), str(tmp_path), ["headings", "formatting"])
        assert issues == []

    def test_lint_missing_file(self, tmp_path):
        issues = lint_file(str(tmp_path / "nope.md"), str(tmp_path), ["formatting"])
        assert len(issues) == 1
        assert "could not read" in issues[0]


# ---------------------------------------------------------------------------
# main / CLI
# ---------------------------------------------------------------------------


class TestMain:
    def test_clean_directory(self, tmp_path):
        f = tmp_path / "good.md"
        f.write_text("# Title\n\nContent.\n")
        result = main([str(tmp_path), "--checks", "headings", "formatting"])
        assert result == 0

    def test_issues_returns_nonzero(self, tmp_path):
        f = tmp_path / "bad.md"
        f.write_text("# Title\n#### Skipped\n")
        result = main([str(tmp_path), "--checks", "headings"])
        assert result == 1

    def test_single_file(self, tmp_path):
        f = tmp_path / "one.md"
        f.write_text("# OK\n\n## Also OK\n\n")
        result = main([str(f), "--checks", "headings"])
        assert result == 0

    def test_invalid_path(self):
        result = main(["/nonexistent/path/xyz"])
        assert result == 1

    def test_quiet_flag(self, tmp_path, capsys):
        f = tmp_path / "test.md"
        f.write_text("# Title\n#### Skip\n")
        main([str(tmp_path), "--checks", "headings", "--quiet"])
        captured = capsys.readouterr()
        # Quiet mode should still show the report
        assert "STYLE GUIDE LINT REPORT" in captured.out


class TestBuildParser:
    def test_defaults(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.path == "."
        assert "html" in args.checks
        assert ".md" in args.extensions
        assert args.quiet is False
