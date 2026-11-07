import io
import json
import unittest
from zipfile import ZipFile

from latex_export import escape, paragraph_sources, project_zip


def exported(markdown, **kwargs):
    with ZipFile(io.BytesIO(project_zip(markdown, **kwargs))) as archive:
        return {name: archive.read(name).decode("utf-8") for name in archive.namelist()}


class LatexExportTests(unittest.TestCase):
    def test_standalone_korean_project_has_root_main_fragment_and_original(self):
        original = "# 한글 연구 제목\n\n## 제3장 방법\n\n### 3.1 설계\n\n관측했다.\n"
        files = exported(original, metadata={"scope": "section", "section_id": "methods"})
        self.assertIn(r"\usepackage{xeCJK}", files["main.tex"])
        self.assertIn("Noto Serif CJK KR", files["main.tex"])
        self.assertIn(r"\title{\Large\bfseries 한글 연구 제목}", files["main.tex"])
        self.assertIn(r"\xeCJKsetup{CJKspace=true}", files["main.tex"])
        self.assertIn(r"\input{content.tex}", files["main.tex"])
        self.assertIn(r"\section*{제3장 방법}", files["content.tex"])
        self.assertIn(r"\subsection*{3.1 설계}", files["content.tex"])
        self.assertNotIn("한글 연구 제목", files["content.tex"])
        self.assertEqual(files["original.md"], original)
        self.assertEqual(json.loads(files["export.json"])["compiler"], "XeLaTeX")
        self.assertNotIn("\\documentclass", files["content.tex"])

    def test_text_special_characters_are_escaped_without_changing_math(self):
        source = r"관측 A_B는 50% & #1이다. $\frac{\alpha_1}{2} \leq 3$이고 `x_y=$2`이다."
        body = exported(source)["content.tex"]
        self.assertIn(r"A\_B는 50\% \& \#1", body)
        self.assertIn(r"\(\frac{\alpha_1}{2} \leq 3\)", body)
        self.assertIn(r"\texttt{x\_y=\$2}", body)
        self.assertIn(r"\textbackslash{}", escape("\\"))
        self.assertIn(r"\textasciitilde{}", exported(r"1\~2ms")["content.tex"])

    def test_all_math_delimiters_survive_and_code_is_not_math(self):
        markdown = "$$\nx_1 + y_2 = 3\n$$\n\n" + r"\(\mu\text{s}\)와 \[a^2+b^2\]" + "\n\n```text\n$not_math$\n```"
        body = exported(markdown)["content.tex"]
        self.assertIn("\\[\nx_1 + y_2 = 3\n\\]", body)
        self.assertIn(r"\(\mu\text{s}\)", body)
        self.assertIn(r"\[a^2+b^2\]", body)
        self.assertIn(r"\$not\_math\$", body)

    def test_table_values_line_breaks_and_math_have_balanced_longtable(self):
        files = exported("| 구성 | 값 |\n| --- | ---: |\n| A_B | 1.23 $\\mu\\text{s}$<br>50% |\n| CPU & GPU | 2 |")
        body = files["content.tex"]
        self.assertEqual(body.count(r"\begin{longtable}"), 1)
        self.assertEqual(body.count(r"\end{longtable}"), 1)
        self.assertIn(r"A\_B", body)
        self.assertIn(r"1.23 \(\mu\text{s}\)\newline{}50\%", body)
        self.assertIn(r"CPU \& GPU", body)
        self.assertIn(r"\endhead", body)

    def test_links_lists_and_code_escape_tex_commands(self):
        source = "3. **첫 조건**\n4. *둘째 조건*\n\n" + r"[원문](https://example.com/a_b?x=1&y=2#part)" + "\n\n```text\n\\input{private} & 5%\n\\end{alltt}\n```"
        body = exported(source)["content.tex"]
        self.assertIn(r"\begin{enumerate}[start=3]", body)
        self.assertIn(r"\textbf{첫 조건}", body)
        self.assertIn(r"\emph{둘째 조건}", body)
        self.assertIn(r"\href{https://example.com/a\_b?x=1\&y=2\#part}{원문}", body)
        self.assertNotIn(r"\input{private}", body)
        self.assertIn(r"\textbackslash{}end\{alltt\}", body)

    def test_unsupported_image_and_control_math_are_reported_without_fetching(self):
        files = exported(r"![측정 결과](https://example.com/private.png)" + "\n\n" + r"$\input{private}$")
        warnings = json.loads(files["export.json"])["warnings"]
        self.assertEqual(len(warnings), 2)
        self.assertIn("측정 결과", files["content.tex"])
        self.assertNotIn(r"\input{private}", files["content.tex"])

    def test_provenance_is_preserved_separately_without_fabricated_bibliography(self):
        fact = dict(id="E1", statement="원문 사실", sources=[dict(page=3, element_id="p3:e4", quote="관측했다.")])
        provenance = paragraph_sources({"s": "### 제목\n\n관측했다. [근거:E1]"}, {"facts": [fact]})
        files = exported("# 연구\n\n관측했다.", provenance=provenance)
        links = json.loads(files["provenance.json"])
        self.assertEqual(links[0]["evidence"][0]["sources"][0]["page"], 3)
        self.assertNotIn(r"\cite", files["content.tex"])
        self.assertNotIn("references.bib", files)

    def test_empty_draft_is_not_exported(self):
        with self.assertRaisesRegex(ValueError, "완성된 본문"):
            project_zip("  ")


if __name__ == "__main__":
    unittest.main()
