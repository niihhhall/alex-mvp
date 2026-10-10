import json
import unittest

from alex import card as cardmod
from alex import diff, inline, llm, mermaid, scoring, text
from alex.findings import from_engine, suggestion_applies

DIFF = """diff --git a/app/webhook.py b/app/webhook.py
index 715e981..12f52c2 100644
--- a/app/webhook.py
+++ b/app/webhook.py
@@ -262,4 +262,8 @@ async def _process(
         # skip
         pass
 
+        # 2. Mark as read (blue ticks)
+        last_msg_id_bytes = await redis_client.redis.get(f"last_msg_id:{phone}")
+        last_msg_id = last_msg_id_bytes.decode('utf-8') if last_msg_id_bytes else ""
+
         if last_msg_id:
diff --git a/app/old.py b/app/old.py
deleted file mode 100644
--- a/app/old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-x = 1
-y = 2
"""

ENGINE = {
    "status": "complete",
    "comments": [
        {"path": "app/webhook.py", "start_line": 267, "end_line": 267, "severity": "critical", "category": "bug",
         "content": "`redis.get` already returns a str \u2014 calling `.decode()` raises AttributeError. Use it directly.",
         "existing_code": "        last_msg_id = last_msg_id_bytes.decode('utf-8') if last_msg_id_bytes else \"\"",
         "suggestion_code": "        last_msg_id = last_msg_id_bytes or \"\""},
        {"path": "app/other.py", "start_line": 10, "end_line": 12, "severity": "low", "category": "style",
         "content": "Name is unclear."},
    ],
}


class TextTests(unittest.TestCase):
    def test_no_dashes_outside_code(self):
        self.assertEqual(text.no_dashes("a \u2014 b, 1\u20132"), "a, b, 1-2")

    def test_dashes_kept_in_code(self):
        src = "x \u2014 y `a\u2014b`\n```\nc \u2014 d\n```"
        self.assertEqual(text.no_dashes(src), "x, y `a\u2014b`\n```\nc \u2014 d\n```")

    def test_first_sentence(self):
        self.assertEqual(text.first_sentence("`foo` breaks here. More text."), "Foo breaks here")


class ScoringTests(unittest.TestCase):
    def test_priority_mapping(self):
        self.assertEqual(scoring.priority("critical", "bug"), "P0")
        self.assertEqual(scoring.priority("high", "style"), "P1")
        self.assertEqual(scoring.priority("medium", "security"), "P1")
        self.assertEqual(scoring.priority("medium", "style"), "P2")
        self.assertEqual(scoring.priority("low", "bug"), "P2")

    def test_caps(self):
        self.assertEqual(scoring.final_score(5, ["P0"]), 2)
        self.assertEqual(scoring.final_score(5, ["P1", "P1"]), 3)
        self.assertEqual(scoring.final_score(5, ["P1"]), 4)
        self.assertEqual(scoring.final_score(1, []), 4)
        self.assertEqual(scoring.final_score("bad", ["P2"]), 4)
        self.assertEqual(scoring.final_score(5, []), 5)

    def test_dots(self):
        self.assertEqual(scoring.dots(3), "\u25CF\u25CF\u25CF\u25CB\u25CB")


class DiffTests(unittest.TestCase):
    def test_commentable_lines(self):
        lines = diff.commentable_lines(DIFF)
        self.assertEqual(lines["app/webhook.py"], set(range(262, 270)))
        self.assertNotIn("app/old.py", lines)

    def test_file_stats(self):
        stats = diff.file_stats(DIFF)
        self.assertEqual(stats[0], {"path": "app/webhook.py", "added": 4, "removed": 0})
        self.assertEqual(stats[1]["removed"], 2)


class FindingTests(unittest.TestCase):
    def setUp(self):
        self.findings = from_engine(ENGINE, diff.commentable_lines(DIFF))

    def test_order_and_placement(self):
        first, second = self.findings
        self.assertEqual((first.number, first.priority, first.placeable), (1, "P0", True))
        self.assertEqual((second.priority, second.placeable), ("P2", False))

    def test_content_cleaned(self):
        self.assertNotIn("\u2014", self.findings[0].content)

    def test_suggestion(self):
        self.assertTrue(suggestion_applies(self.findings[0]))

    def test_inline_body_and_dedupe(self):
        f = self.findings[0]
        payload = inline.review_comment(f)
        self.assertEqual((payload["line"], payload["side"]), (267, "RIGHT"))
        self.assertIn("```suggestion", payload["body"])
        self.assertIn(f"alex-finding:{f.fingerprint}", payload["body"])
        already = inline.existing_fingerprints([{"body": payload["body"], "html_url": "u"}])
        self.assertEqual(inline.to_post(self.findings, set(already)), [])


class MermaidTests(unittest.TestCase):
    def test_valid_flowchart(self):
        src = 'flowchart TD\n  A["Incoming message"] --> B["decode fails"]'
        self.assertIsNotNone(mermaid.validate("flowchart", src))

    def test_rejects_unquoted_parens(self):
        self.assertIsNone(mermaid.validate("flowchart", "flowchart TD\n  A[call foo()] --> B"))

    def test_rejects_wrong_header(self):
        self.assertIsNone(mermaid.validate("sequence", "flowchart TD\n A --> B"))

    def test_real_case1_flowchart_passes(self):
        src = '''flowchart TD
  A["Webhook message arrives"] --> B["Get last_msg_id from Redis"]
  B --> C{"Value present?"}
  C -->|"No"| D["Skip read receipt"]
  C -->|"Yes"| E["Call decode on str value"]
  E --> F["AttributeError raised"]
  F --> G["Outer except aborts processing"]
  G --> H["No blue ticks, no reply"]'''
        self.assertIsNotNone(mermaid.validate("flowchart", src))

    def test_real_dropped_diagram_now_passes(self):
        src = '''flowchart TD
  A["Incoming webhook message"] --> B["_process_with_interrupt_protection"]
  B --> C["redis.get last_msg_id:phone"]
  C --> D{"Value returned?"}
  D -- "str, decode_responses=True" --> E["Call .decode('utf-8') on str"]
  D -- "None" --> F["last_msg_id = empty string"]
  E --> G["AttributeError: str has no attribute decode"]
  G --> H["Outer except Exception swallows error"]
  H --> I["Abort before set_generating and process_conversation"]
  I --> J["No reply sent, no blue ticks"]
  F --> K["Continue to mark as read"]'''
        self.assertIsNotNone(mermaid.validate("flowchart", src))

    def test_flowchart_rejects_bad_lines(self):
        ok = 'flowchart TD\n  D -- "str, decode_responses=True" --> E["Call .decode(\'utf-8\') on str"]'
        self.assertIsNotNone(mermaid.validate("flowchart", ok))
        for bad in ('A -- text --> B', 'A ==> B ==', 'A["ok"] --> B["x"] extra words', 'style A fill:#f00',
                    'A["quote " inside"] --> B'):
            self.assertIsNone(mermaid.validate("flowchart", f"flowchart TD\n  {bad}"), bad)

    def test_sequence_rules(self):
        good = "sequenceDiagram\n  participant W as Webhook\n  W->>R: get last_msg_id\n  R-->>W: str\n  Note over W: decode fails\n  alt has id\n  W->>W: decode\n  end"
        self.assertIsNotNone(mermaid.validate("sequence", good))
        self.assertIsNone(mermaid.validate("sequence", "sequenceDiagram\n  W->>R get id"))
        self.assertIsNone(mermaid.validate("sequence", "sequenceDiagram\n  W=>R: x"))

    def test_er_and_class(self):
        self.assertIsNotNone(mermaid.validate("er", 'erDiagram\n  LEAD ||--o{ BOOKING : has\n  BOOKING {\n  string calendly_event_id UK\n  }'))
        self.assertIsNotNone(mermaid.validate("class", "classDiagram\n  Router <|-- CloudRouter\n  Router : +send()"))
        self.assertIsNone(mermaid.validate("er", "erDiagram\n  LEAD -> BOOKING"))
        self.assertIsNone(mermaid.validate("er", "erDiagram\n  BOOKING {\n  string id"))

    def test_strips_fences(self):
        out = mermaid.validate("sequence", "```mermaid\nsequenceDiagram\n  A->>B: hi\n```")
        self.assertEqual(out, "sequenceDiagram\n  A->>B: hi")


class CardTests(unittest.TestCase):
    def setUp(self):
        self.findings = from_engine(ENGINE, diff.commentable_lines(DIFF))

    def test_normalize_clamps_and_validates(self):
        raw = {"impact": "high", "headline": "Adds read receipts", "verdict": "Fix it.", "summary": ["a", "b"],
               "files": {"app/webhook.py": "read receipts"}, "titles": {"1": "Replies stop for every user"},
               "score": 5, "diagram": {"type": "flowchart", "mermaid": 'flowchart TD\n A["x"] --> B["y"]'}}
        card = cardmod.normalize(raw, self.findings)
        self.assertEqual((card.impact, card.score, card.diagram_type), ("High", 2, "flowchart"))
        cardmod.apply_titles(card, self.findings)
        self.assertEqual(self.findings[0].title, "Replies stop for every user")

    def test_apply_diagram(self):
        card = cardmod.normalize(None, self.findings)
        self.assertTrue(cardmod.apply_diagram(card, {"type": "flowchart", "mermaid": 'flowchart TD\n A["a"] --> B["b"]'}))
        self.assertEqual(card.diagram_type, "flowchart")
        broken = cardmod.normalize(None, self.findings)
        self.assertFalse(cardmod.apply_diagram(broken, {"type": "flowchart", "mermaid": "flowchart TD\n A -- x --> B"}))
        self.assertIsNone(broken.diagram)
        self.assertTrue(broken.diagram_rejected.startswith("flowchart"))
        self.assertFalse(cardmod.apply_diagram(broken, None))

    def test_fallback_card(self):
        card = cardmod.normalize(None, self.findings)
        self.assertFalse(card.from_model)
        self.assertEqual(card.score, 2)
        self.assertIn("P0", card.verdict)

    def test_render(self):
        card = cardmod.normalize(None, self.findings)
        md = cardmod.render(card, self.findings, diff_text=DIFF, review_count=2, head_sha="2911559abc",
                            head_message="Mark as read", commit_url="https://x/commit/2911559")
        self.assertTrue(md.startswith(cardmod.SUMMARY_MARKER))
        self.assertIn("Confidence 2/5", md)
        self.assertIn("(not on a changed line)", md)
        self.assertIn("Reviews (2)", md)
        self.assertNotIn("\u2014", md)
        self.assertEqual(cardmod.read_meta(md)["reviews"], 2)


class LLMTests(unittest.TestCase):
    def test_parse_json_variants(self):
        self.assertEqual(llm.parse_json('{"a": 1}'), {"a": 1})
        self.assertEqual(llm.parse_json('Sure:\n```json\n{"a": 2}\n```'), {"a": 2})
        self.assertEqual(llm.parse_json('<think>hmm {x}</think>{"a": 3}'), {"a": 3})
        self.assertIsNone(llm.parse_json("no json"))

    def test_build_messages_includes_findings(self):
        findings = from_engine(ENGINE, diff.commentable_lines(DIFF))
        msgs = cardmod.build_messages("t", "", DIFF, findings)
        payload = msgs[1]["content"]
        self.assertIn("app/webhook.py:267", payload)
        json.loads(payload.split("Findings (2):\n")[1].split("\n\nDiff:")[0])


if __name__ == "__main__":
    unittest.main()
