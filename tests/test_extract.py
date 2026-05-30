from __future__ import annotations

from trip_planner.ingest.extract import extract_main_text

HTML = """<!doctype html>
<html lang="en">
  <head><title>Best Ramen in Tokyo</title></head>
  <body>
    <article>
      <h1>Best Ramen in Tokyo</h1>
      <p>Tokyo is a paradise for ramen lovers, with hundreds of specialised shops scattered
         across every neighbourhood. From rich, milky tonkotsu broth simmered for many hours
         to delicate shoyu and fragrant miso, each district has its own celebrated style.</p>
      <p>Start in Shinjuku for late-night bowls, then explore the back streets of Shibuya and
         Ikebukuro where small counters seat barely a dozen guests and queues form well before
         opening time. Bring cash, slurp loudly, and order a side of gyoza.</p>
    </article>
  </body>
</html>"""


def test_title_and_language() -> None:
    result = extract_main_text(HTML, url="https://example.com/ramen")
    assert result.title == "Best Ramen in Tokyo"
    assert result.language == "en"


def test_text_and_word_count() -> None:
    result = extract_main_text(HTML, url="https://example.com/ramen")
    assert result.text and "ramen" in result.text.lower()
    assert result.word_count > 20


def test_empty_html() -> None:
    result = extract_main_text(None)
    assert result.word_count == 0
    assert result.text is None
