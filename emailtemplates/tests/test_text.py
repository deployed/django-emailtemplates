# coding=utf-8
from django.test import SimpleTestCase

from ..text import html_to_text

EMAIL = """<!DOCTYPE html>
<html>
  <head><title>Order 7</title><style>p { color: red; }</style></head>
  <body>
    <span style="display: none">Thank you for your order</span>
    <table width="100%"><tr><td>
      <h1>Hello Anna &amp; Tom,</h1>
      <p>Your order is confirmed.<br />Pay here: <a href="https://shop.example.com/pay/7/">Pay now</a></p>
      <ul><li>Course A</li><li>Course B</li></ul>
      <script>alert(1)</script>
    </td></tr></table>
  </body>
</html>"""


class HtmlToTextTest(SimpleTestCase):
    def setUp(self):
        self.text = html_to_text(EMAIL)

    def test_text_of_the_email(self):
        self.assertIn("Hello Anna & Tom,", self.text)
        self.assertIn("Your order is confirmed.\nPay here:", self.text)
        self.assertIn("Course A", self.text)
        self.assertIn("Course B", self.text)

    def test_links_keep_their_address(self):
        self.assertIn("Pay now", self.text)
        self.assertIn("https://shop.example.com/pay/7/", self.text)

    def test_head_styles_scripts_and_hidden_elements_are_left_out(self):
        for left_out in ("Order 7", "color: red", "alert", "Thank you for your order"):
            self.assertNotIn(left_out, self.text)

    def test_no_markup_and_no_trailing_spaces(self):
        self.assertNotIn("<", self.text)
        self.assertFalse(any(line != line.rstrip() for line in self.text.splitlines()))
        self.assertNotIn("\n\n\n", self.text)
        self.assertEqual(self.text, self.text.strip())

    def test_paragraphs_start_their_own_lines(self):
        self.assertEqual(
            html_to_text("<h1>Title</h1><p>First</p><p>Second</p>").splitlines(),
            ["Title", "", "First", "", "Second"],
        )

    def test_empty_input(self):
        self.assertEqual(html_to_text(""), "")
        self.assertEqual(html_to_text(None), "")
